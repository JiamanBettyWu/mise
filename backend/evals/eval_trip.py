"""Trip-planner offline eval (#30) — manual, dev-only, NOT scheduled.

Run from the repo root:

    uv --project backend run python backend/evals/eval_trip.py

Running THIS file is the opt-in (same pattern as jobs/trace_trip.py): nothing
on the Render request path or the GitHub crons imports it, and `weave` is a
dev-only dependency.

What it grades: the real pipeline downstream of the fetch nodes. The eval
graph reuses the production node functions verbatim but starts from an
injected forecast + the frozen catalog in datasets/trips.json — live OWM would
make rows non-reproducible and its 5-day window would constrain scenarios.
Everything else is real: the Sonnet reason_and_select call, the Haiku query
planner (which reads live profile/preferences from Supabase), and the SerpAPI
product search (best-effort; failures keep gaps visible with results=[]).
~8 cases ≈ cents per run.
"""

import argparse
import asyncio
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# Init weave BEFORE importing the pipeline, so the Anthropic autopatch is in
# place before services.claude builds its client.
import weave  # noqa: E402

from observability import init_weave  # noqa: E402

TRACING = init_weave()

from langgraph.graph import END, START, StateGraph  # noqa: E402

from evals import scorers  # noqa: E402
from schemas import ClothingItem, TripWeather  # noqa: E402
from services.trip_planner import (  # noqa: E402
    PackingState,
    check_gaps,
    generate_output_node,
    infer_weather_if_needed_node,
    plan_purchase_queries_node,
    reason_and_select_node,
    search_purchases_node,
)

DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "trips.json"


def build_eval_graph():
    """The production graph minus the two fetch nodes.

    get_weather / get_catalog are replaced by seeding `weather` and `catalog`
    in the initial state; every downstream node is the real one, including the
    climate-inference call for partial/inferred coverage cases.
    """
    g = StateGraph(PackingState)
    g.add_node("infer_weather_if_needed", infer_weather_if_needed_node)
    g.add_node("reason_and_select", reason_and_select_node)
    g.add_node("plan_purchase_queries", plan_purchase_queries_node)
    g.add_node("search_purchases", search_purchases_node)
    g.add_node("generate_output", generate_output_node)

    g.add_edge(START, "infer_weather_if_needed")
    g.add_edge("infer_weather_if_needed", "reason_and_select")
    g.add_conditional_edges(
        "reason_and_select",
        check_gaps,
        {"has_gaps": "plan_purchase_queries", "no_gaps": "generate_output"},
    )
    g.add_edge("plan_purchase_queries", "search_purchases")
    g.add_edge("search_purchases", "generate_output")
    g.add_edge("generate_output", END)
    return g.compile()


_EVAL_APP = build_eval_graph()
_FIXTURES = json.loads(DATASET_PATH.read_text())
_CATALOG = [ClothingItem(**row) for row in _FIXTURES["catalog"]]


@weave.op
def plan_trip(
    case_id: str,
    destination: str,
    start_date: str,
    end_date: str,
    additional_notes: str,
    weather: dict,
) -> dict:
    """Task under evaluation: one eval-graph run, returned as a plain dict so
    scorers (and the Weave UI) see JSON, not pydantic objects."""
    initial_state: PackingState = {
        "destination": destination,
        "start_date": date.fromisoformat(start_date),
        "end_date": date.fromisoformat(end_date),
        "additional_notes": additional_notes,
        "weather": TripWeather(**weather),
        "catalog": _CATALOG,
    }
    final = _EVAL_APP.invoke(initial_state)
    return {
        "weather_summary": final["weather"].summary,
        "packing_list": [
            c.model_dump(mode="json") for c in final.get("packing_list", [])
        ],
        "gaps": [g.model_dump(mode="json") for g in final.get("gaps", [])],
        "purchase_suggestions": [
            s.model_dump(mode="json") for s in final.get("purchase_suggestions", [])
        ],
        "essentials": final.get("essentials", []),
        "reasoning": final.get("reasoning", ""),
    }


# Thin weave wrappers over the pure scorers: bind the frozen catalog and map
# dataset columns (matched by parameter name) onto the scorer signatures.


@weave.op
def items_in_catalog(output: dict) -> dict:
    return scorers.items_in_catalog(output, _FIXTURES["catalog"])


@weave.op
def outfit_completeness(output: dict) -> dict:
    return scorers.outfit_completeness(output)


@weave.op
def quantity_for_duration(output: dict, start_date: str, end_date: str) -> dict:
    duration = (date.fromisoformat(end_date) - date.fromisoformat(start_date)).days + 1
    return scorers.quantity_for_duration(output, duration)


@weave.op
def cold_requires_warm_layer(output: dict, weather: dict) -> dict:
    return scorers.cold_requires_warm_layer(output, weather)


@weave.op
def gaps_surface_as_suggestions(output: dict) -> dict:
    return scorers.gaps_surface_as_suggestions(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Runs per case (weave.Evaluation trials). Use 3 when measuring "
        "a variance fix (#120) — n=1 can't distinguish a fix from a coin flip.",
    )
    args = parser.parse_args()

    if not TRACING:
        print(
            "[eval] weave init failed — aborting; an eval run whose results "
            "aren't recorded is money spent on nothing (fix WANDB_API_KEY or "
            "`uv add --dev weave`)."
        )
        return 1

    evaluation = weave.Evaluation(
        evaluation_name="trip-planner-code-checks",
        dataset=_FIXTURES["cases"],
        trials=args.trials,
        scorers=[
            items_in_catalog,
            outfit_completeness,
            quantity_for_duration,
            cold_requires_warm_layer,
            gaps_surface_as_suggestions,
        ],
    )
    summary = asyncio.run(evaluation.evaluate(plan_trip))
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
