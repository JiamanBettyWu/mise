"""Tests for the outfit-refinement LangGraph (#145).

Offline by default, same posture as test_graph.py: graph shape, the router's
fail-open default, the refine node's deterministic guards (with create_tracked
and the combo lookups patched), and the checkpointer's turn accumulation are
all exercised without network or Supabase.
"""

import json
from types import SimpleNamespace

import pytest

import services.outfit_refine as refine_mod
from services.modes import DAILY_MODES, mode_by_name
from services.outfit_refine import (
    RefineError,
    build_graph,
    check_route,
    refine,
    refine_outfit_node,
    route_node,
)

WEATHER = {
    "temp_high_c": 24,
    "temp_low_c": 15,
    "conditions": "clear",
    "precip_chance": 0.1,
    "wind_kmh": 10,
}

POOL = [
    {"id": "top1", "name": "White tee", "type": "t-shirt"},
    {"id": "bot1", "name": "Black jeans", "type": "jeans"},
    {"id": "shoe1", "name": "Sneakers", "type": "sneakers"},
    {"id": "shoe2", "name": "Loafers", "type": "shoes"},
]


def fake_resp(payload):
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=json.dumps(payload))],
        stop_reason="end_turn",
    )


def base_state(**overrides):
    state = {
        "history_id": "hid",
        "mode": "Smart casual",
        "weather": WEATHER,
        "notes": "",
        "current_item_ids": ["top1", "bot1", "shoe1"],
        "user_message": "swap the shoes",
        "turns": ["swap the shoes"],
        "candidate_pool": POOL,
    }
    state.update(overrides)
    return state


def patch_combos(monkeypatch, blocked=(), recent=()):
    monkeypatch.setattr(refine_mod, "blocked_combos", lambda: set(blocked))
    monkeypatch.setattr(refine_mod, "recent_combos", lambda: set(recent))


# ---------------------------------------------------------------- graph shape


def test_graph_nodes_and_edges():
    nodes = set(build_graph().get_graph().nodes)
    assert {"load_context", "route", "refine_outfit", "regenerate", "persist"} <= nodes


def test_check_route_reads_state():
    assert check_route({"route": "refine"}) == "refine"
    assert check_route({"route": "regenerate"}) == "regenerate"


# --------------------------------------------------------------------- router


def test_route_node_parses_classification(monkeypatch):
    monkeypatch.setattr(
        refine_mod, "create_tracked", lambda *a, **k: fake_resp({"route": "regenerate"})
    )
    assert route_node(base_state())["route"] == "regenerate"


def test_route_node_fails_open_to_refine(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("api down")

    monkeypatch.setattr(refine_mod, "create_tracked", boom)
    assert route_node(base_state())["route"] == "refine"


def test_route_node_rejects_unknown_label(monkeypatch):
    monkeypatch.setattr(
        refine_mod, "create_tracked", lambda *a, **k: fake_resp({"route": "vibes"})
    )
    assert route_node(base_state())["route"] == "refine"


# ---------------------------------------------------------------- refine node


def test_refine_swaps_items(monkeypatch):
    patch_combos(monkeypatch)
    monkeypatch.setattr(
        refine_mod,
        "create_tracked",
        lambda *a, **k: fake_resp(
            {"item_ids": ["top1", "bot1", "shoe2"], "reasoning": "loafers instead"}
        ),
    )
    out = refine_outfit_node(base_state())
    assert out["current_item_ids"] == ["top1", "bot1", "shoe2"]
    assert out["reasoning"] == "loafers instead"


def test_refine_rejects_blocked_combo(monkeypatch):
    patch_combos(monkeypatch, blocked=[frozenset({"top1", "bot1", "shoe2"})])
    monkeypatch.setattr(
        refine_mod,
        "create_tracked",
        lambda *a, **k: fake_resp(
            {"item_ids": ["top1", "bot1", "shoe2"], "reasoning": "swap"}
        ),
    )
    out = refine_outfit_node(base_state())
    assert "current_item_ids" not in out
    assert "previously disliked" in out["reasoning"]


def test_refine_rejects_recent_repeat(monkeypatch):
    patch_combos(monkeypatch, recent=[frozenset({"top1", "bot1", "shoe2"})])
    monkeypatch.setattr(
        refine_mod,
        "create_tracked",
        lambda *a, **k: fake_resp(
            {"item_ids": ["top1", "bot1", "shoe2"], "reasoning": "swap"}
        ),
    )
    out = refine_outfit_node(base_state())
    assert "current_item_ids" not in out
    assert "repeat" in out["reasoning"]


def test_refine_unchanged_set_passes_recent_guard(monkeypatch):
    # The current outfit is itself a recent combo (its row is logged); an
    # unchanged answer must not trip the repeat guard.
    current = frozenset({"top1", "bot1", "shoe1"})
    patch_combos(monkeypatch, recent=[current])
    monkeypatch.setattr(
        refine_mod,
        "create_tracked",
        lambda *a, **k: fake_resp(
            {"item_ids": ["top1", "bot1", "shoe1"], "reasoning": "kept"}
        ),
    )
    out = refine_outfit_node(base_state())
    assert out["current_item_ids"] == ["top1", "bot1", "shoe1"]


def test_refine_filters_hallucinated_ids_and_repairs_structure(monkeypatch):
    patch_combos(monkeypatch)
    # Two footwear entries → structural violation → drop_extras keeps one;
    # "ghost" isn't in the pool → filtered before validation.
    monkeypatch.setattr(
        refine_mod,
        "create_tracked",
        lambda *a, **k: fake_resp(
            {
                "item_ids": ["top1", "bot1", "shoe1", "shoe2", "ghost"],
                "reasoning": "swap",
            }
        ),
    )
    out = refine_outfit_node(base_state())
    ids = out["current_item_ids"]
    assert "ghost" not in ids
    assert len([i for i in ids if i.startswith("shoe")]) == 1


# --------------------------------------------------------------- checkpointer


def test_thread_accumulates_turns_and_builds_pool_once(monkeypatch):
    built = []

    def fake_load(state):
        if state.get("candidate_pool"):
            return {}
        built.append(state["history_id"])
        return {"candidate_pool": POOL}

    monkeypatch.setattr(refine_mod, "load_context_node", fake_load)
    monkeypatch.setattr(refine_mod, "route_node", lambda s: {"route": "refine"})
    monkeypatch.setattr(
        refine_mod,
        "refine_outfit_node",
        lambda s: {"current_item_ids": ["top1"], "reasoning": "ok"},
    )
    monkeypatch.setattr(refine_mod, "persist_node", lambda s: {})

    app = build_graph()
    cfg = {"configurable": {"thread_id": "hid"}}

    def invoke_input(msg, **kw):
        # What refine() actually sends: row-derived fields + this turn's
        # message — never the pool, which only the checkpointer carries.
        state = base_state(user_message=msg, turns=[msg], **kw)
        del state["candidate_pool"]
        return state

    def turn(msg):
        return app.invoke(invoke_input(msg), config=cfg)

    turn("swap the shoes")
    final = turn("something warmer")
    assert final["turns"] == ["swap the shoes", "something warmer"]
    assert built == ["hid"]  # pool assembled on the first turn only

    # A different thread starts a fresh conversation.
    other = app.invoke(
        {**invoke_input("hi"), "history_id": "other"},
        config={"configurable": {"thread_id": "other"}},
    )
    assert other["turns"] == ["hi"]
    assert built == ["hid", "other"]


# ------------------------------------------------------------------ pre-DB guards


def test_refine_rejects_empty_message():
    with pytest.raises(RefineError) as exc:
        refine("hid", "   ")
    assert exc.value.status == 422


# ------------------------------------------------------------------ streaming


ROW = {
    "id": "hid",
    "recommended_on": "2026-01-01",
    "mode": "Smart casual",
    "item_ids": ["top1", "bot1", "shoe1"],
    "weather": WEATHER,
    "notes": "",
}


def _patch_stream_graph(monkeypatch, route="refine"):
    # Same rebuild trick as test_graph.py: _APP was compiled at import with
    # the original node functions, so patch the nodes, then swap in a fresh
    # build_graph() that picks them up.
    monkeypatch.setattr(
        refine_mod, "load_context_node", lambda s: {"candidate_pool": POOL}
    )
    monkeypatch.setattr(refine_mod, "route_node", lambda s: {"route": route})
    monkeypatch.setattr(
        refine_mod,
        "refine_outfit_node",
        lambda s: {
            "current_item_ids": ["top1", "bot1", "shoe2"],
            "reasoning": "swapped",
        },
    )
    monkeypatch.setattr(refine_mod, "persist_node", lambda s: {})
    monkeypatch.setattr(refine_mod, "_APP", refine_mod.build_graph())
    monkeypatch.setattr(refine_mod, "_load_row", lambda hid, msg: (ROW, msg))
    monkeypatch.setattr(
        refine_mod,
        "_hydrate",
        lambda hid, row, final: {
            "history_id": hid,
            "label": row["mode"],
            "items": final["current_item_ids"],
            "reasoning": final.get("reasoning", ""),
            "route": final.get("route", "refine"),
        },
    )


def test_stream_yields_stages_then_outfit_then_done(monkeypatch):
    _patch_stream_graph(monkeypatch)
    events = list(refine_mod.stream("hid", "swap the shoes"))
    kinds = [e for e, _ in events]

    # Stages name what's running NEXT (updates-mode reports completions):
    # context up front, routing after load_context, restyling after route.
    stages = [p["stage"] for e, p in events if e == "progress"]
    assert stages == ["context", "routing", "restyling"]
    assert kinds[-2:] == ["outfit", "done"]

    outfit = events[kinds.index("outfit")][1]
    assert outfit["items"] == ["top1", "bot1", "shoe2"]
    assert outfit["route"] == "refine"


def test_stream_validation_raises_before_any_event(monkeypatch):
    # RefineError must escape at call time (→ a real HTTP status), not
    # surface mid-stream after headers are gone.
    def bad_row(hid, msg):
        raise RefineError("outfit not found", 404)

    monkeypatch.setattr(refine_mod, "_load_row", bad_row)
    with pytest.raises(RefineError):
        refine_mod.stream("hid", "swap the shoes")


def _outfits_stream_client():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from auth import require_password
    from routers import outfits as outfits_router

    app = FastAPI()
    app.include_router(outfits_router.router)
    app.dependency_overrides[require_password] = lambda: None
    return TestClient(app)


def _parse_sse(text):
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


def test_refine_stream_route_happy_path(monkeypatch):
    _patch_stream_graph(monkeypatch)
    resp = _outfits_stream_client().post(
        "/outfits/hid/refine/stream", json={"message": "swap the shoes"}
    )
    assert resp.status_code == 200
    kinds = [e for e, _ in _parse_sse(resp.text)]
    assert kinds[-2:] == ["outfit", "done"]


def test_refine_stream_route_validation_is_http_error(monkeypatch):
    def bad_row(hid, msg):
        raise RefineError("outfit not found", 404)

    monkeypatch.setattr(refine_mod, "_load_row", bad_row)
    resp = _outfits_stream_client().post(
        "/outfits/hid/refine/stream", json={"message": "swap"}
    )
    assert resp.status_code == 404


def test_refine_stream_route_mid_stream_error_becomes_error_event(monkeypatch):
    _patch_stream_graph(monkeypatch)

    def boom(s):
        raise RuntimeError("api down")

    monkeypatch.setattr(refine_mod, "refine_outfit_node", boom)
    monkeypatch.setattr(refine_mod, "_APP", refine_mod.build_graph())

    resp = _outfits_stream_client().post(
        "/outfits/hid/refine/stream", json={"message": "swap"}
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert "error" in kinds
    assert kinds[-1] == "done"


def test_recommend_stream_route_relays_stages_and_result(monkeypatch):
    def fake_recommend(*, on_stage=None, **kw):
        on_stage("weather")
        on_stage("styling")
        return {"weather": {}, "outfits": [], "wardrobe_size": 0}

    monkeypatch.setattr("routers.outfits.recommend", fake_recommend)
    resp = _outfits_stream_client().post("/outfits/recommend/stream", json={})
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    kinds = [e for e, _ in events]
    assert [p["stage"] for e, p in events if e == "progress"] == ["weather", "styling"]
    assert kinds[-2:] == ["result", "done"]


def test_recommend_stream_route_failure_becomes_error_event(monkeypatch):
    def fake_recommend(**kw):
        raise RuntimeError("boom")

    monkeypatch.setattr("routers.outfits.recommend", fake_recommend)
    resp = _outfits_stream_client().post("/outfits/recommend/stream", json={})
    assert resp.status_code == 200
    kinds = [e for e, _ in _parse_sse(resp.text)]
    assert "error" in kinds
    assert kinds[-1] == "done"


# ---------------------------------------------------------------------- modes


def test_daily_modes_moved_intact():
    assert [m["name"] for m in DAILY_MODES] == [
        "Smart casual",
        "Athleisure",
        "Elevated",
    ]
    assert mode_by_name("Elevated")["description"]
    assert mode_by_name("(default)") is None
