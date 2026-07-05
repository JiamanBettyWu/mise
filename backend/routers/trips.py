import json
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth import require_password
from db.supabase import client as supabase
from schemas import (
    TripPlanRequest,
    TripPlanResponse,
    TripPlanSaved,
    TripPlanSaveRequest,
    TripPlanSummary,
)
from services import trip_planner
from services.weather import DestinationNotFound

log = logging.getLogger("wardrobe.trips")

router = APIRouter(
    prefix="/trips",
    tags=["trips"],
    dependencies=[Depends(require_password)],
)


@router.post("/plan", response_model=TripPlanResponse)
def plan(req: TripPlanRequest) -> TripPlanResponse:
    if req.end_date < req.start_date:
        raise HTTPException(
            status_code=400, detail="end_date must be on or after start_date"
        )
    try:
        return trip_planner.run(req)
    except DestinationNotFound as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        log.error("Trip planning failed:\n%s", traceback.format_exc())
        raise HTTPException(status_code=502, detail="Trip planning failed")


def _sse_frame(event: str, payload: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


@router.post("/plan/stream")
def plan_stream(req: TripPlanRequest) -> StreamingResponse:
    if req.end_date < req.start_date:
        raise HTTPException(
            status_code=400, detail="end_date must be on or after start_date"
        )

    # No eager peek here on purpose: get_weather and get_catalog fan out from
    # START and race, so pulling the first event before headers go out only
    # turns DestinationNotFound into a clean 400 when get_weather happens to
    # win — any OTHER first-superstep failure (a Supabase/OWM outage) would
    # escape uncaught as a raw 500, since there'd be nothing here to catch it.
    # Degrading every failure to an `error` + `done` frame inside generate()
    # gives one deterministic contract instead of a race-dependent split.
    def generate():
        try:
            for event, payload in trip_planner.stream(req):
                yield _sse_frame(event, payload)
        except DestinationNotFound as e:
            yield _sse_frame("error", {"detail": str(e)})
            yield _sse_frame("done", {})
        except Exception:
            log.error("Trip planning stream failed:\n%s", traceback.format_exc())
            yield _sse_frame("error", {"detail": "Trip planning failed"})
            yield _sse_frame("done", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---- Saved trip plans (#128) ------------------------------------------------
# Explicit save only — nothing above this line ever writes to trip_plans.
# `plan` is stored and returned verbatim; POST validates it against
# TripPlanResponse on the way in, but GET never re-validates the frozen
# snapshot through the (possibly since-evolved) live schema.

TRIP_SUMMARY_COLUMNS = "id,created_at,destination,start_date,end_date,notes,edited"


@router.post("", response_model=TripPlanSaved)
def save_trip(req: TripPlanSaveRequest) -> TripPlanSaved:
    row = {
        "destination": req.destination,
        "start_date": req.start_date.isoformat(),
        "end_date": req.end_date.isoformat(),
        "notes": req.notes,
        "plan": req.plan.model_dump(mode="json"),
        "edited": req.edited,
    }
    res = supabase().table("trip_plans").insert(row).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Insert returned no row")
    return TripPlanSaved(**res.data[0])


@router.get("", response_model=list[TripPlanSummary])
def list_trips() -> list[TripPlanSummary]:
    res = (
        supabase()
        .table("trip_plans")
        .select(TRIP_SUMMARY_COLUMNS)
        .order("created_at", desc=True)
        .execute()
    )
    return [TripPlanSummary(**row) for row in (res.data or [])]


@router.get("/{trip_id}", response_model=TripPlanSaved)
def get_trip(trip_id: str) -> TripPlanSaved:
    res = supabase().table("trip_plans").select("*").eq("id", trip_id).execute()
    if not res.data:
        raise HTTPException(status_code=404, detail="Trip not found")
    return TripPlanSaved(**res.data[0])


@router.delete("/{trip_id}", status_code=204)
def delete_trip(trip_id: str) -> None:
    existing = supabase().table("trip_plans").select("id").eq("id", trip_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Trip not found")
    supabase().table("trip_plans").delete().eq("id", trip_id).execute()
