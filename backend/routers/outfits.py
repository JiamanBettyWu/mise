import json
import logging
import threading
import traceback
from datetime import datetime, timezone
from queue import Queue
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from auth import require_password
from db.supabase import client as supabase
from services import outfit_refine
from services.outfit_history import AttributionError, record_attribution
from services.outfit_refine import RefineError, refine
from services.recommend import recommend

log = logging.getLogger("wardrobe.outfits")

router = APIRouter(
    prefix="/outfits",
    tags=["outfits"],
    dependencies=[Depends(require_password)],
)


class RecommendRequest(BaseModel):
    travel_mode: bool = False
    notes: str = ""
    n: int = Field(default=3, ge=1, le=5)
    lat: float | None = Field(default=None, ge=-90, le=90)
    lon: float | None = Field(default=None, ge=-180, le=180)
    # Experiment flag (#137): dev/eval probes set persist=False so trial runs
    # never land in outfit_history (they'd phantom-penalize items via recency
    # and skew the diversity report). The web Generate button omits it → True.
    persist: bool = True


class FeedbackRequest(BaseModel):
    verdict: Literal[-1, 0, 1]


class AttributionRequest(BaseModel):
    reason: Literal["specific_items", "combination", "weather", "occasion"] | None = (
        None
    )
    item_ids: list[str] = []
    note: str = ""


@router.post("/{history_id}/feedback")
def record_feedback(history_id: str, req: FeedbackRequest):
    """Authed in-app twin of the email link (GET /feedback/{token}) — #41.

    Same row, same semantics, different auth: the app already sends
    X-App-Password, so no token needed. verdict 0 clears the verdict (the
    web thumbs toggle off; email links can't do that). Latest write wins
    across both channels.

    Every web tap is a clear or a change (toggle semantics), so attribution
    fields are wiped unconditionally — attribution belongs to the verdict
    act it followed (#60).
    """
    verdict = req.verdict or None
    res = (
        supabase()
        .table("outfit_history")
        .update(
            {
                "feedback": verdict,
                "feedback_at": (
                    datetime.now(timezone.utc).isoformat() if verdict else None
                ),
                "feedback_reason": None,
                "feedback_item_ids": None,
                "feedback_note": None,
            }
        )
        .eq("id", history_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Outfit not found")
    return {"history_id": history_id, "feedback": verdict}


@router.post("/{history_id}/attribution")
def record_feedback_attribution(history_id: str, req: AttributionRequest):
    """Optional 👎 follow-up from the web chips (#60).

    Strictly optional — the verdict was already recorded by the feedback
    endpoint; this adds the "why". Refused unless the row's current verdict
    is 👎 (latest write wins across channels, so it may have changed).
    """
    try:
        record_attribution(history_id, req.reason, req.item_ids, req.note)
    except AttributionError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    return {"history_id": history_id, "recorded": True}


class RefineRequest(BaseModel):
    message: str = Field(min_length=1, max_length=500)


@router.post("/{history_id}/refine")
def refine_outfit(history_id: str, req: RefineRequest):
    """One multi-turn refinement turn (#145). history_id doubles as the
    LangGraph thread_id, so repeat calls continue the same conversation."""
    try:
        return refine(history_id, req.message)
    except RefineError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    except Exception:
        log.error("Refinement failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail="Refinement failed")


@router.post("/recommend")
def recommend_endpoint(req: RecommendRequest):
    try:
        return recommend(
            travel_mode=req.travel_mode,
            notes=req.notes,
            n=req.n,
            lat=req.lat,
            lon=req.lon,
            persist=req.persist,
        )
    except Exception as e:
        log.error("Recommendation failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail="Recommendation failed")


def _sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


_SSE_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}


@router.post("/recommend/stream")
def recommend_stream(req: RecommendRequest) -> StreamingResponse:
    """SSE twin of /recommend (#154): `progress` frames per stage, then a
    `result` frame with the full recommend() payload, then `done`.

    recommend() is deliberately straight-line Python (not a graph), so there's
    no node stream to relay — instead it runs in a worker thread reporting
    stages through a queue the generator drains. Same error model as
    /trips/plan/stream: post-headers failures degrade to `error` + `done`
    frames. A client disconnect leaves the worker to finish (and persist) on
    its own — same as the blocking endpoint's behavior on abandon.
    """

    def generate():
        q: Queue = Queue()

        def worker():
            try:
                result = recommend(
                    travel_mode=req.travel_mode,
                    notes=req.notes,
                    n=req.n,
                    lat=req.lat,
                    lon=req.lon,
                    persist=req.persist,
                    on_stage=lambda s: q.put(("progress", {"stage": s})),
                )
                q.put(("result", result))
            except Exception:
                log.error("Recommendation stream failed:\n%s", traceback.format_exc())
                q.put(("error", {"detail": "Recommendation failed"}))
            finally:
                q.put(("done", {}))

        threading.Thread(target=worker, daemon=True).start()
        while True:
            event, payload = q.get()
            yield _sse_frame(event, payload)
            if event == "done":
                return

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=_SSE_HEADERS
    )


@router.post("/{history_id}/refine/stream")
def refine_outfit_stream(history_id: str, req: RefineRequest) -> StreamingResponse:
    """SSE twin of /refine (#154): `progress` frames per graph node, then an
    `outfit` frame with the revised outfit, then `done`. Validation runs
    eagerly in outfit_refine.stream(), so bad requests still get real HTTP
    statuses; only post-headers failures degrade to `error` + `done` frames.
    """
    try:
        events = outfit_refine.stream(history_id, req.message)
    except RefineError as e:
        raise HTTPException(status_code=e.status, detail=str(e))

    def generate():
        try:
            for event, payload in events:
                yield _sse_frame(event, payload)
        except Exception:
            log.error("Refinement stream failed:\n%s", traceback.format_exc())
            yield _sse_frame("error", {"detail": "Refinement failed"})
            yield _sse_frame("done", {})

    return StreamingResponse(
        generate(), media_type="text/event-stream", headers=_SSE_HEADERS
    )
