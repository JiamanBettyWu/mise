"""Tests for the trip planner LangGraph.

Offline by default — graph shape, router, and the purchase stub are pure.
The full pipeline (weather + Supabase + Claude) is opt-in via RUN_E2E=1 and
uses dynamic dates inside OWM's 5-day forecast window, so it never goes
stale the way hardcoded dates did.
"""

import os
from datetime import date, timedelta

import pytest

from schemas import Gap, TripPlanRequest
from services.trip_planner import build_graph, check_gaps, search_purchases_node

A_GAP = Gap(item="rain jacket", rationale="daily rain", category="outerwear")


def test_graph_shape():
    # Replaces the old eyeball-only mermaid print with assertions: all nodes
    # present, the linear spine wired, and the conditional fork out of
    # reason_and_select reaching both branches.
    g = build_graph().get_graph()
    nodes = set(g.nodes)
    assert {
        "get_weather",
        "infer_weather_if_needed",
        "get_catalog",
        "reason_and_select",
        "search_purchases",
        "generate_output",
    } <= nodes
    edges = {(e.source, e.target) for e in g.edges}
    assert ("get_weather", "infer_weather_if_needed") in edges
    assert ("infer_weather_if_needed", "get_catalog") in edges
    assert ("get_catalog", "reason_and_select") in edges
    assert ("search_purchases", "generate_output") in edges
    fork_targets = {t for s, t in edges if s == "reason_and_select"}
    assert {"search_purchases", "generate_output"} <= fork_targets


def test_check_gaps_router():
    assert check_gaps({"gaps": [A_GAP]}) == "has_gaps"
    assert check_gaps({"gaps": []}) == "no_gaps"
    assert check_gaps({}) == "no_gaps"  # key missing entirely


def test_search_purchases_stub():
    out = search_purchases_node({"gaps": [A_GAP]})
    assert "purchase_suggestions" in out, "node must return the state key"
    sugg = out["purchase_suggestions"]
    assert len(sugg) == 1 and sugg[0].gap.item == "rain jacket"
    assert sugg[0].results[0].retailer == "Example"


@pytest.mark.skipif(
    os.environ.get("RUN_E2E") != "1",
    reason="hits OWM + Supabase + Anthropic; opt in with RUN_E2E=1",
)
def test_full_pipeline_end_to_end():
    from services.trip_planner import run

    start = date.today() + timedelta(days=1)  # inside the live OWM window
    req = TripPlanRequest(
        destination="Oaxaca, Mexico",
        start_date=start,
        end_date=start + timedelta(days=3),
        additional_notes="City exploring, Monte Albán ruins, cobblestones",
    )
    resp = run(req)
    assert resp.weather.coverage in ("full_forecast", "partial_forecast")
    assert resp.packing_list, "expected a non-empty packing list"
