"""Manual Weave trace run for the trip planner (#85) — NOT scheduled.

Run by hand to see the trip-planner LangGraph as a Weave call tree:

    uv --project backend run python jobs/trace_trip.py

Running THIS file is the opt-in to tracing. Nothing schedules it, and the graph
module never imports weave, so ordinary planner requests (the /trip router) stay
untraced (observability off the hot path, #85 guardrail).

No decorators are added to trip_planner.py: the graph is a LangChain Runnable,
so Weave's LangChain integration auto-traces the whole run (nodes + the patched
Anthropic calls) once init_weave() has run. This launcher exists to see whether
that auto-trace is legible enough on its own before deciding if any surgical
@op is warranted.

⚠️ This is a REAL run: every node calls Claude and search_purchases_node hits
SerpAPI (live quota). Unlike trace_daily.py there's no persist=False lever, but
the planner writes nothing to the DB, so it only spends API budget.
"""

import logging
import sys
from datetime import date, timedelta
from pathlib import Path

# Make `services`, `observability`, etc. importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Init tracing BEFORE importing the graph, so the Anthropic autopatch AND the
# LangChain callback handler are installed before trip_planner builds its client
# and compiles the graph at module load.
from observability import init_weave, op  # noqa: E402

init_weave()

from schemas import TripPlanRequest, TripPlanResponse  # noqa: E402
from services import trip_planner  # noqa: E402


@op(name="plan_trip")
def plan_trip(req: TripPlanRequest) -> TripPlanResponse:
    """Named trace root so the top-level call reads `plan_trip` instead of the
    integration's default `langchain.Chain.LangGraph`. The LangGraph auto-trace
    (and its nodes) nests underneath this op."""
    return trip_planner.run(req)


# A sample trip a few days out. The dates straddle the OWM 5-day forecast window
# on purpose, so the trace also exercises infer_weather_if_needed's climate call.
SAMPLE_TRIP = TripPlanRequest(
    destination="Paris, France",
    start_date=date.today() + timedelta(days=10),
    end_date=date.today() + timedelta(days=20),
    additional_notes="Walking the city and markets; a couple of nicer dinners.",
)


def main() -> int:
    result = plan_trip(SAMPLE_TRIP)
    print(
        f"[trace] {SAMPLE_TRIP.destination}: "
        f"{len(result.packing_list)} packing categories, "
        f"{len(result.gaps)} gap(s), "
        f"{len(result.purchase_suggestions)} purchase suggestion(s)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
