import logging
import traceback
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_password
from db.supabase import client as supabase
from services.outfit_history import AttributionError, record_attribution
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


class FeedbackRequest(BaseModel):
    verdict: Literal[-1, 0, 1]


class AttributionRequest(BaseModel):
    reason: Literal["specific_items", "combination", "weather", "occasion"] | None = None
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


@router.post("/recommend")
def recommend_endpoint(req: RecommendRequest):
    try:
        return recommend(
            travel_mode=req.travel_mode,
            notes=req.notes,
            n=req.n,
            lat=req.lat,
            lon=req.lon,
        )
    except Exception as e:
        log.error("Recommendation failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail="Recommendation failed")
