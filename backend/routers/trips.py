import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException

from auth import require_password
from schemas import TripPlanRequest, TripPlanResponse
from services import trip_planner

log = logging.getLogger("wardrobe.trips")

router = APIRouter(
    prefix="/trips",
    tags=["trips"],
    dependencies=[Depends(require_password)],
)


@router.post("/plan", response_model=TripPlanResponse)
def plan(req: TripPlanRequest) -> TripPlanResponse:
    if req.end_date < req.start_date:
        raise HTTPException(status_code=400, detail="end_date must be on or after start_date")
    try:
        return trip_planner.run(req)
    except Exception as e:
        log.error("Trip planning failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail=f"{type(e).__name__}: {e}")
