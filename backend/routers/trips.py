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

    events = trip_planner.stream(req)
    # Pull the first event eagerly, before headers go out: get_weather and
    # get_catalog fan out from START and race, so this only turns into a real
    # 400 when get_weather's DestinationNotFound is the first thing the graph
    # yields (e.g. get_catalog hasn't returned yet). If get_catalog wins the
    # race, the same failure surfaces later as a mid-stream `error` event
    # instead — both are handled, so this is an optimization, not a guarantee.
    try:
        first = next(events, None)
    except DestinationNotFound as e:
        raise HTTPException(400, str(e))

    def generate():
        try:
            if first is not None:
                yield _sse_frame(*first)
            for event, payload in events:
                yield _sse_frame(event, payload)
        except DestinationNotFound as e:
            # Same failure as the eager-peek 400 above, just arriving after
            # get_catalog won the START race — keep the specific message
            # instead of falling through to the generic one below.
            yield _sse_frame("error", {"detail": str(e)})
            yield _sse_frame("done", {})
        except Exception:
            log.error("Trip planning stream failed:\n%s", traceback.format_exc())
            yield _sse_frame("error", {"detail": "Trip planning failed"})
            yield _sse_frame("done", {})

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache"},
    )
