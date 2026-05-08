import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from auth import require_password
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


@router.post("/recommend")
def recommend_endpoint(req: RecommendRequest):
    try:
        return recommend(travel_mode=req.travel_mode, notes=req.notes, n=req.n)
    except Exception as e:
        log.error("Recommendation failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")
