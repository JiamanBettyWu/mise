import json
import logging
import traceback

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

from auth import require_password
from schemas import TripPlanRequest, TripPlanResponse
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
