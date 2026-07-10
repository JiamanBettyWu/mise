"""Daily-recommender offline eval (#118) — manual, dev-only, NOT scheduled.

Run from the repo root:

    uv --project backend run python backend/evals/eval_recommend.py [--trials 3]

Running THIS file is the opt-in (same pattern as eval_trip.py): nothing on the
Render request path or the GitHub crons imports it, and `weave` is a dev-only
dependency. ~5 cases ≈ cents per run (one Sonnet call each).

What it grades: the real `services.recommend.recommend()` path — extremes
gate → recency/feedback-weighted sampling → the Sonnet outfit call with
feedback context and combo blocklists — over a frozen scenario instead of
live fetches. datasets/recommend.json carries the injected pieces: a catalog
snapshot, a 14-day outfit_history window (the recency/feedback substrate),
and synthetic weather cases; `persist=False` keeps eval runs out of
outfit_history (#137). Preferences still read live from Supabase, same
trade-off as eval_trip's Haiku planner.

This is the before/after measuring stick for the variety fix (#135): run it
on main, apply a sampler change (DAILY_DECAY, SAMPLE_FRACTION,
SMALL_CATEGORY_MAX, floors), run again with --trials 3, and compare
repeat_gap's fresh_fraction / mean_gap_days in Weave while the structural
scorers guard against regressions. The companion diversity_report.py
diagnoses the same thing on real history after a fix ships.

Refresh the dataset by re-dumping catalog + trailing history (see the
_comment field in the JSON) — but scores are only comparable within one
dataset version, so refresh between experiments, not mid-experiment.
"""

import argparse
import asyncio
import json
import logging
import sys
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

from datetime import date  # noqa: E402

from evals import recommend_scorers  # noqa: E402
from services.claude import OUTFIT_SYSTEM_PROMPT  # noqa: E402
from services.recommend import RECOMMEND_CONFIG, recommend  # noqa: E402

DATASET_PATH = Path(__file__).resolve().parent / "datasets" / "recommend.json"

_FIXTURES = json.loads(DATASET_PATH.read_text())
_CATALOG = _FIXTURES["catalog"]
_HISTORY = _FIXTURES["history"]
_MODES_BY_NAME = {m["name"]: m for m in _FIXTURES["modes"]}


@weave.op
def recommend_day(
    case_id: str, today: str, mode_names: list[str], notes: str, weather: dict
) -> dict:
    """Task under evaluation: one frozen-scenario recommend() run, reduced to
    the fields the scorers need (ids + labels; hydrated rows stay in the
    trace)."""
    result = recommend(
        notes=notes,
        modes=[_MODES_BY_NAME[name] for name in mode_names],
        persist=False,
        weather=weather,
        wardrobe=_CATALOG,
        history_rows=_HISTORY,
        today=date.fromisoformat(today),
    )
    return {
        "outfits": [
            {
                "label": o["label"],
                "item_ids": [item["id"] for item in o["items"]],
                "item_names": [item.get("name") for item in o["items"]],
                "reasoning": o["reasoning"],
            }
            for o in result["outfits"]
        ],
    }


# Thin weave wrappers over the pure scorers: bind the frozen fixtures and map
# dataset columns (matched by parameter name) onto the scorer signatures.


@weave.op
def valid_structure(output: dict) -> dict:
    return recommend_scorers.valid_structure(output, _CATALOG)


@weave.op
def items_in_catalog(output: dict) -> dict:
    return recommend_scorers.items_in_catalog(output, _CATALOG)


@weave.op
def no_gate_violations(output: dict, weather: dict) -> dict:
    return recommend_scorers.no_gate_violations(output, weather, _CATALOG)


@weave.op
def repeat_gap(output: dict, today: str) -> dict:
    return recommend_scorers.repeat_gap(output, _HISTORY, _CATALOG, today)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--trials",
        type=int,
        default=1,
        help="Runs per case (weave.Evaluation trials). Sampling is stochastic "
        "by design, so use 3 when comparing sampler configs — n=1 can't "
        "distinguish a fix from a lucky draw.",
    )
    args = parser.parse_args()

    if not TRACING:
        print(
            "[eval] weave init failed — aborting; an eval run whose results "
            "aren't recorded is money spent on nothing (fix WANDB_API_KEY or "
            "`uv add --dev weave`)."
        )
        return 1

    # Publish the prompt under test as a content-versioned Weave object (#143):
    # same text → same version, edited text → new version with a diff in the
    # Weave UI. Dev-only by construction — only this launcher imports weave.
    # RECOMMEND_CONFIG["prompt_sha"] is the join key back to the git-derived
    # cohort labels on live outfit_history rows.
    weave.publish(weave.StringPrompt(OUTFIT_SYSTEM_PROMPT), name="outfit-system-prompt")
    print(f"[eval] recommend config: {json.dumps(RECOMMEND_CONFIG)}")

    evaluation = weave.Evaluation(
        evaluation_name="daily-recommender-code-checks",
        dataset=_FIXTURES["cases"],
        trials=args.trials,
        scorers=[valid_structure, items_in_catalog, no_gate_violations, repeat_gap],
    )
    summary = asyncio.run(evaluation.evaluate(recommend_day))
    print(json.dumps(summary, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
