import logging
import traceback
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_password
from db.supabase import client as supabase
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


@router.post("/{history_id}/feedback")
def record_feedback(history_id: str, req: FeedbackRequest):
    """Authed in-app twin of the email link (GET /feedback/{token}) — #41.

    Same row, same semantics, different auth: the app already sends
    X-App-Password, so no token needed. verdict 0 clears the verdict (the
    web thumbs toggle off; email links can't do that). Latest write wins
    across both channels.
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
            }
        )
        .eq("id", history_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=404, detail="Outfit not found")
    return {"history_id": history_id, "feedback": verdict}


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
