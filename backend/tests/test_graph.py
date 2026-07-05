"""Tests for the trip planner LangGraph.

Offline by default — graph shape, router, and the purchase node (with
search_products patched) are pure. The full pipeline (weather + Supabase +
Claude) is opt-in via RUN_E2E=1 and uses dynamic dates inside OWM's 5-day
forecast window, so it never goes stale the way hardcoded dates did.
"""

import json
import os
from datetime import date, datetime, timedelta

import pytest

from schemas import (
    Gap,
    PackingPlanOutput,
    PurchaseQuery,
    PurchaseResult,
    PurchaseSuggestion,
    TripPlanRequest,
    TripWeather,
)
from services.trip_planner import (
    PURCHASE_QUERY_SYSTEM_PROMPT,
    _build_purchase_query_prompt,
    build_graph,
    check_gaps,
    fallback_purchase_query,
    plan_purchase_queries_node,
    search_purchases_node,
)

A_GAP = Gap(item="rain jacket", rationale="daily rain", category="outerwear")


def _stream_req():
    return TripPlanRequest(
        destination="Paris, France",
        start_date=date(2026, 7, 10),
        end_date=date(2026, 7, 12),
        additional_notes="",
    )


def _patch_front_half(monkeypatch, gaps):
    # Stubs weather/catalog/reasoning so stream() tests focus on event
    # shape/ordering, not the underlying node behavior (covered elsewhere).
    monkeypatch.setattr(
        "services.trip_planner.get_weather_node",
        lambda s: {"weather": TripWeather(summary="Sunny.", coverage="full_forecast")},
    )
    monkeypatch.setattr(
        "services.trip_planner.get_catalog_node", lambda s: {"catalog": []}
    )
    monkeypatch.setattr(
        "services.trip_planner.reason_and_select_node",
        lambda s: {
            "candidate_items": [],
            "gaps": gaps,
            "reasoning": "r",
            "essentials": [],
        },
    )


def _use_patched_graph(monkeypatch):
    # `_APP` is compiled once at module load with direct references to the
    # node functions in scope at that time (see build_graph's docstring
    # comment) — monkeypatching a node name afterwards doesn't reach it.
    # Rebuilding after all node patches are in place picks them up, since
    # build_graph() looks the names up in the module namespace at call time.
    from services.trip_planner import build_graph

    monkeypatch.setattr("services.trip_planner._APP", build_graph())


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
        "plan_purchase_queries",
        "search_purchases",
        "generate_output",
    } <= nodes
    edges = {(e.source, e.target) for e in g.edges}
    # #2: weather and catalog fan out from START in parallel...
    assert ("__start__", "get_weather") in edges
    assert ("__start__", "get_catalog") in edges
    assert ("get_weather", "infer_weather_if_needed") in edges
    # ...and both branches join before reason_and_select.
    assert ("infer_weather_if_needed", "reason_and_select") in edges
    assert ("get_catalog", "reason_and_select") in edges
    assert ("plan_purchase_queries", "search_purchases") in edges
    # #124: generate_output now runs right after reason_and_select (it's pure
    # Python and never needed purchase results), and the has_gaps/no_gaps fork
    # moves from reason_and_select to generate_output.
    assert ("reason_and_select", "generate_output") in edges
    assert ("search_purchases", "__end__") in edges
    fork_targets = {t for s, t in edges if s == "generate_output"}
    assert {"plan_purchase_queries", "__end__"} <= fork_targets


def test_fanout_joins_before_reason_and_select(monkeypatch):
    # #2: the weather branch (2 steps) and catalog branch (1 step) fan out from
    # START and must BOTH complete before reason_and_select fires. With naive
    # per-edge joins the shorter catalog branch would trigger it a superstep
    # early, before infer_weather_if_needed had merged its state.
    seen = {}

    monkeypatch.setattr(
        "services.trip_planner.get_weather_node",
        lambda s: {"weather": TripWeather(summary="Sunny.", coverage="full_forecast")},
    )
    monkeypatch.setattr(
        "services.trip_planner.get_catalog_node", lambda s: {"catalog": []}
    )

    def _fake_reason(state):
        seen["weather"] = state.get("weather")
        seen["catalog"] = state.get("catalog")
        return {"candidate_items": [], "gaps": [], "reasoning": "", "essentials": []}

    monkeypatch.setattr("services.trip_planner.reason_and_select_node", _fake_reason)

    build_graph().invoke(
        {
            "destination": "Paris, France",
            "start_date": date(2026, 7, 10),
            "end_date": date(2026, 7, 12),
            "additional_notes": "",
        }
    )
    assert seen["weather"] is not None, "weather branch must finish before reasoning"
    assert seen["catalog"] is not None, "catalog branch must finish before reasoning"


def test_check_gaps_router():
    assert check_gaps({"gaps": [A_GAP]}) == "has_gaps"
    assert check_gaps({"gaps": []}) == "no_gaps"
    assert check_gaps({}) == "no_gaps"  # key missing entirely


def test_reason_and_select_reads_parsed_output(monkeypatch):
    # #123: structured outputs guarantee the shape (no missing keys, no
    # malformed gaps — replaces the #120/#122 defensive parsing this deleted).
    # recommend_packing_plan returns a validated PackingPlanOutput directly.
    from services import trip_planner

    parsed = PackingPlanOutput(
        item_ids=["abc"],
        gaps=[Gap(item="rain jacket", rationale="daily rain", category="outerwear")],
        essentials=["sunscreen"],
        reasoning="r",
    )
    monkeypatch.setattr(trip_planner, "recommend_packing_plan", lambda blocks: parsed)

    out = trip_planner.reason_and_select_node(
        {
            "destination": "Lisbon",
            "start_date": date(2026, 7, 10),
            "end_date": date(2026, 7, 12),
            "additional_notes": "",
            "weather": TripWeather(summary="warm", coverage="full_forecast", daily=[]),
            "catalog": [],
        }
    )
    assert out["candidate_items"] == []  # "abc" isn't in the empty catalog
    assert out["gaps"] == parsed.gaps
    assert out["reasoning"] == "r"
    assert out["essentials"] == ["sunscreen"]


def test_search_purchases_node_builds_suggestions(monkeypatch):
    # The node imported search_products via `from services.search import ...`,
    # which binds the name in trip_planner's namespace — so patch it there,
    # not in services.search (patching the source module wouldn't reach this
    # already-bound reference).
    fake = PurchaseResult(
        title="Rain Jacket",
        url="https://shop.example/rain-jacket",
        image_url="https://img.example/rj.jpg",
        price="$89.00",
        retailer="ShopCo",
    )
    monkeypatch.setattr(
        "services.trip_planner.search_products",
        lambda query, num=4: [fake],
    )
    out = search_purchases_node({"gaps": [A_GAP]})
    assert "purchase_suggestions" in out, "node must return the state key"
    sugg = out["purchase_suggestions"]
    assert len(sugg) == 1
    assert sugg[0].gap.item == "rain jacket"
    assert sugg[0].results == [fake]


def test_search_purchases_node_uses_planned_query(monkeypatch):
    calls = []

    def _fake_search(query, num=4):
        calls.append(query)
        return []

    monkeypatch.setattr("services.trip_planner.search_products", _fake_search)

    out = search_purchases_node(
        {
            "gaps": [A_GAP],
            "purchase_queries": [
                PurchaseQuery(
                    gap_index=0,
                    query="women's lightweight neutral rain jacket city travel",
                )
            ],
        }
    )

    assert calls == ["women's lightweight neutral rain jacket city travel"]
    assert out["purchase_suggestions"][0].gap == A_GAP


def test_search_purchases_node_keeps_gaps_without_results(monkeypatch):
    # Even when search yields nothing (no key, API down, or zero hits), the gap
    # must still surface as a suggestion with an empty results list.
    monkeypatch.setattr(
        "services.trip_planner.search_products",
        lambda query, num=4: [],
    )
    out = search_purchases_node({"gaps": [A_GAP]})
    sugg = out["purchase_suggestions"]
    assert len(sugg) == 1
    assert sugg[0].gap.item == "rain jacket"
    assert sugg[0].results == []


def test_search_purchases_node_isolates_per_query_failures(monkeypatch):
    # #107: gap searches run concurrently; one raising search must not sink
    # the siblings — the failed gap surfaces with results=[].
    other_gap = Gap(item="sun hat", rationale="strong sun", category="accessories")
    fake = PurchaseResult(title="Sun Hat", url="https://shop.example/sun-hat")

    def _fake_search(query, num=4):
        if "rain" in query:
            raise RuntimeError("boom")
        return [fake]

    monkeypatch.setattr("services.trip_planner.search_products", _fake_search)

    out = search_purchases_node({"gaps": [A_GAP, other_gap]})
    sugg = out["purchase_suggestions"]
    assert len(sugg) == 2
    assert sugg[0].gap == A_GAP and sugg[0].results == []
    assert sugg[1].gap == other_gap and sugg[1].results == [fake]


def test_search_purchases_node_preserves_gap_order(monkeypatch):
    # Concurrent execution must not reorder suggestions relative to gaps.
    gaps = [
        Gap(item=f"item {i}", rationale="r", category="accessories") for i in range(5)
    ]
    monkeypatch.setattr(
        "services.trip_planner.search_products",
        lambda query, num=4: [PurchaseResult(title=query, url="https://x.example/")],
    )
    out = search_purchases_node({"gaps": gaps})
    assert [s.gap.item for s in out["purchase_suggestions"]] == [g.item for g in gaps]
    assert [s.results[0].title for s in out["purchase_suggestions"]] == [
        g.item for g in gaps
    ]


def test_fallback_purchase_query_uses_department_for_apparel():
    assert fallback_purchase_query(A_GAP, "womens") == "women's rain jacket"
    assert fallback_purchase_query(A_GAP, "mens") == "men's rain jacket"
    assert fallback_purchase_query(A_GAP, "no_preference") == "rain jacket"


def test_fallback_purchase_query_skips_department_for_accessories():
    gap = Gap(
        item="travel adapter",
        rationale="international outlets",
        category="accessories",
    )
    assert fallback_purchase_query(gap, "womens") == "travel adapter"


def test_plan_purchase_queries_node_falls_back_when_planner_fails(monkeypatch):
    monkeypatch.setattr(
        "services.trip_planner._get_purchase_context",
        lambda: ("womens", [], []),
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("bad json")

    monkeypatch.setattr("services.trip_planner.plan_purchase_queries", _boom)

    out = plan_purchase_queries_node({"gaps": [A_GAP]})

    assert out["shopping_department"] == "womens"
    assert out["purchase_queries"] == [
        PurchaseQuery(
            gap_index=0,
            query="women's rain jacket",
            rationale="Fallback query used because the planner did not return a usable query.",
        )
    ]


def test_packing_prompt_trims_catalog_but_keeps_warmth():
    # #2: the catalog payload drops fields irrelevant to styling (photo_url,
    # available, in_travel_bag, notes, created_at) but must keep `warmth` —
    # it's the cold/heat signal the weather reasoning depends on (#40).
    from schemas import ClothingItem
    from services.trip_planner import _build_packing_prompt

    item = ClothingItem(
        id="00000000-0000-0000-0000-000000000001",
        name="Wool coat",
        type="coat",
        color="camel",
        formality="smart-casual",
        season="winter",
        fabric="wool",
        warmth=5,
        description="Heavy winter coat",
        brand="Acme",
        notes="dry clean only",
        photo_url="https://img.example/coat.jpg",
        available=True,
        in_travel_bag=False,
        created_at=datetime(2026, 1, 1),
    )
    blocks = _build_packing_prompt(
        {
            "destination": "Oslo, Norway",
            "start_date": date(2026, 12, 1),
            "end_date": date(2026, 12, 5),
            "additional_notes": "",
            "weather": TripWeather(summary="Cold.", coverage="inferred_climate"),
            "catalog": [item],
        }
    )
    catalog_json = blocks[-1]
    sent = json.loads(catalog_json)[0]
    assert sent["id"] == item.id
    assert sent["warmth"] == 5
    for dropped in ("photo_url", "available", "in_travel_bag", "notes", "created_at"):
        assert dropped not in sent


def test_purchase_query_prompt_carries_preferences_as_applicability_context():
    state = {
        "destination": "Paris, France",
        "start_date": date(2026, 7, 1),
        "end_date": date(2026, 7, 4),
        "additional_notes": "museum days and dinners",
        "weather": TripWeather(
            summary="Mild with scattered rain.",
            coverage="inferred_climate",
        ),
        "gaps": [A_GAP],
    }

    blocks = _build_purchase_query_prompt(
        state,
        shopping_department="womens",
        user_preferences=["Avoid bright logos"],
        inferred_preferences=["Prefers sandals over sneakers in athleisure outfits"],
    )
    prompt = "\n\n".join(blocks)

    assert "shopping_department: womens" in prompt
    assert '"gap_index": 0' in prompt
    assert "User-authored preferences (hard constraints only when applicable)" in prompt
    assert "Learned preferences (soft hints; ignore when irrelevant)" in prompt
    assert "Avoid bright logos" in prompt
    assert "Prefers sandals over sneakers" in prompt
    assert "It is valid to use no preferences" in PURCHASE_QUERY_SYSTEM_PROMPT
    assert "Do not force outfit-composition preferences" in PURCHASE_QUERY_SYSTEM_PROMPT


def test_stream_yields_plan_before_purchases_when_gaps(monkeypatch):
    # #124: generate_output's plan event must be observable before
    # search_purchases's purchases event, and done is always last.
    _patch_front_half(monkeypatch, gaps=[A_GAP])
    monkeypatch.setattr(
        "services.trip_planner.plan_purchase_queries_node",
        lambda s: {"purchase_queries": [], "shopping_department": "womens"},
    )
    monkeypatch.setattr(
        "services.trip_planner.search_purchases_node",
        lambda s: {"purchase_suggestions": [PurchaseSuggestion(gap=A_GAP, results=[])]},
    )
    _use_patched_graph(monkeypatch)

    from services.trip_planner import stream

    events = list(stream(_stream_req()))
    kinds = [e for e, _ in events]

    assert kinds.count("plan") == 1
    assert kinds.count("purchases") == 1
    assert kinds[-1] == "done"
    assert kinds.index("plan") < kinds.index("purchases")

    plan_payload = events[kinds.index("plan")][1]
    assert plan_payload["packing_list"] == []
    assert plan_payload["gaps"][0]["item"] == "rain jacket"

    purchases_payload = events[kinds.index("purchases")][1]
    assert purchases_payload["purchase_suggestions"][0]["gap"]["item"] == "rain jacket"


def test_stream_ends_after_plan_when_no_gaps(monkeypatch):
    # The no-gaps path skips plan_purchase_queries/search_purchases entirely,
    # so no purchases event should ever fire.
    _patch_front_half(monkeypatch, gaps=[])
    _use_patched_graph(monkeypatch)

    from services.trip_planner import stream

    events = list(stream(_stream_req()))
    kinds = [e for e, _ in events]

    assert "purchases" not in kinds
    assert kinds.count("plan") == 1
    assert kinds[-1] == "done"


def _parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for frame in text.strip().split("\n\n"):
        event, data = None, None
        for line in frame.split("\n"):
            if line.startswith("event: "):
                event = line[len("event: ") :]
            elif line.startswith("data: "):
                data = line[len("data: ") :]
        if event is not None and data is not None:
            events.append((event, json.loads(data)))
    return events


def _stream_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth import require_password
    from routers import trips as trips_router

    app = FastAPI()
    app.include_router(trips_router.router)
    app.dependency_overrides[require_password] = lambda: None
    return TestClient(app)


_STREAM_BODY = {
    "destination": "Paris, France",
    "start_date": "2026-07-10",
    "end_date": "2026-07-12",
    "additional_notes": "",
}


def test_plan_stream_route_orders_plan_before_purchases(monkeypatch):
    _patch_front_half(monkeypatch, gaps=[A_GAP])
    monkeypatch.setattr(
        "services.trip_planner.plan_purchase_queries_node",
        lambda s: {"purchase_queries": [], "shopping_department": "womens"},
    )
    monkeypatch.setattr(
        "services.trip_planner.search_purchases_node",
        lambda s: {"purchase_suggestions": [PurchaseSuggestion(gap=A_GAP, results=[])]},
    )
    _use_patched_graph(monkeypatch)

    resp = _stream_client().post("/trips/plan/stream", json=_STREAM_BODY)
    assert resp.status_code == 200
    kinds = [e for e, _ in _parse_sse(resp.text)]
    assert kinds.index("plan") < kinds.index("purchases")
    assert kinds[-1] == "done"


def test_plan_stream_route_mid_stream_error_becomes_error_event(monkeypatch):
    # A failure after the first event has already been pulled (headers sent)
    # can't become an HTTP error status — it must degrade to an `error` event
    # followed by `done`, per the issue's error model.
    _patch_front_half(monkeypatch, gaps=[])
    monkeypatch.setattr(
        "services.trip_planner.generate_output_node",
        lambda s: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    _use_patched_graph(monkeypatch)

    resp = _stream_client().post("/trips/plan/stream", json=_STREAM_BODY)
    assert resp.status_code == 200
    kinds = [e for e, _ in _parse_sse(resp.text)]
    assert "error" in kinds
    assert kinds[-1] == "done"


def test_plan_stream_route_destination_not_found_becomes_error_event(monkeypatch):
    # No eager peek in plan_stream (see routers/trips.py) — every
    # DestinationNotFound, regardless of whether get_weather or get_catalog
    # wins the START race, surfaces as a mid-stream `error` event. This test
    # covers get_catalog mocked to return instantly (so it wins the race);
    # the sibling test below covers the other ordering.
    from services.weather import DestinationNotFound

    monkeypatch.setattr(
        "services.trip_planner.get_weather_node",
        lambda s: (_ for _ in ()).throw(DestinationNotFound("nope")),
    )
    monkeypatch.setattr(
        "services.trip_planner.get_catalog_node", lambda s: {"catalog": []}
    )
    _use_patched_graph(monkeypatch)

    resp = _stream_client().post("/trips/plan/stream", json=_STREAM_BODY)
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert kinds[-1] == "done"
    # The specific DestinationNotFound message must survive losing the race,
    # not fall back to the generic "Trip planning failed".
    error_payload = dict(events)["error"]
    assert error_payload["detail"] == "nope"


def test_plan_stream_route_rejects_bad_date_range():
    resp = _stream_client().post(
        "/trips/plan/stream", json={**_STREAM_BODY, "end_date": "2026-07-01"}
    )
    assert resp.status_code == 400


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
