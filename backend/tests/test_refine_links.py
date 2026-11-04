"""Tests for the email one-tap refine links (#144).

Offline: the refine pipeline itself is covered by test_outfit_refine.py, so
here it is patched out — these tests pin the glue: canned-message mapping,
the token-authed GET endpoint's status mapping, email rendering, and the
job's link attachment.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import routers.feedback as feedback_mod
from routers.feedback import REFINE_MESSAGES
from services.email_template import render_outfit_email
from services.feedback_token import REFINE_KINDS, sign_refine_token
from services.outfit_refine import RefineError

HID = "1f4a2b3c-0000-4000-8000-123456789abc"

WEATHER = {
    "temp_high_c": 24,
    "temp_low_c": 15,
    "conditions": "clear",
    "precip_chance": 0.1,
    "wind_kmh": 10,
}


@pytest.fixture(autouse=True)
def _pin_secret(monkeypatch):
    monkeypatch.setenv("FEEDBACK_SECRET", "test-secret-do-not-use")


def _client():
    app = FastAPI()
    app.include_router(feedback_mod.router)
    return TestClient(app)


# ------------------------------------------------------------------- mapping


def test_every_refine_kind_has_a_canned_message():
    assert set(REFINE_MESSAGES) == set(REFINE_KINDS)
    assert all(msg.strip() for msg in REFINE_MESSAGES.values())


# ------------------------------------------------------------------ endpoint


def test_refine_link_happy_path(monkeypatch):
    calls = []

    def fake_refine(history_id, message, thread_id=None):
        assert thread_id and thread_id.startswith("email-")  # stateless hop
        calls.append((history_id, message))
        return {
            "history_id": history_id,
            "label": "Smart casual",
            "items": [
                {"id": "shoe2", "name": "Loafers", "photo_url": "http://x/l.jpg"}
            ],
            "reasoning": "Loafers instead of sneakers.",
            "route": "refine",
        }

    monkeypatch.setattr(feedback_mod, "refine", fake_refine)
    token = sign_refine_token(HID, "swap_shoes")
    resp = _client().get(f"/feedback/refine/{token}")
    assert resp.status_code == 200
    assert calls == [(HID, REFINE_MESSAGES["swap_shoes"])]
    assert "Loafers" in resp.text
    assert "Loafers instead of sneakers." in resp.text


def test_refine_link_bad_token_is_400(monkeypatch):
    monkeypatch.setattr(
        feedback_mod, "refine", lambda *a, **k: pytest.fail("refine must not run")
    )
    resp = _client().get("/feedback/refine/not-a-token")
    assert resp.status_code == 400
    assert "not valid" in resp.text.lower()


def test_refine_link_maps_refine_error_status(monkeypatch):
    def stale(history_id, message, thread_id=None):
        raise RefineError("refinement is only available for today's outfits", 409)

    monkeypatch.setattr(feedback_mod, "refine", stale)
    resp = _client().get(f"/feedback/refine/{sign_refine_token(HID, 'warmer')}")
    assert resp.status_code == 409
    assert "today" in resp.text


def test_refine_link_unexpected_failure_is_500(monkeypatch):
    def boom(history_id, message, thread_id=None):
        raise RuntimeError("api down")

    monkeypatch.setattr(feedback_mod, "refine", boom)
    resp = _client().get(f"/feedback/refine/{sign_refine_token(HID, 'cooler')}")
    assert resp.status_code == 500


def test_email_clicks_are_stateless_hops(monkeypatch):
    """Review follow-up on #144: an email click must NOT resume the web
    conversation keyed by history_id — each click rebuilds the candidate
    pool against current availability and starts with no prior turns.
    Exercised through the real refine() + graph (MemorySaver intact), with
    the row load, nodes, and hydration patched offline."""
    import services.outfit_refine as refine_mod

    row = {
        "id": HID,
        "recommended_on": "2026-01-01",
        "mode": "Smart casual",
        "item_ids": ["top1", "shoe1"],
        "weather": WEATHER,
        "notes": "",
    }
    # Wardrobe availability as of each pool build; shoe1 goes unavailable
    # between the two clicks.
    available = [[{"id": "top1"}, {"id": "shoe1"}, {"id": "shoe2"}]]
    builds, seen = [], []

    def fake_load(state):
        if state.get("candidate_pool"):
            return {}
        builds.append(state["history_id"])
        return {"candidate_pool": list(available[0])}

    def fake_refine_node(state):
        seen.append(
            {"turns": list(state["turns"]), "pool": list(state["candidate_pool"])}
        )
        return {"current_item_ids": ["top1", "shoe2"], "reasoning": "ok"}

    monkeypatch.setattr(refine_mod, "load_context_node", fake_load)
    monkeypatch.setattr(refine_mod, "route_node", lambda s: {"route": "refine"})
    monkeypatch.setattr(refine_mod, "refine_outfit_node", fake_refine_node)
    monkeypatch.setattr(refine_mod, "persist_node", lambda s: {})
    monkeypatch.setattr(refine_mod, "_APP", refine_mod.build_graph())
    monkeypatch.setattr(refine_mod, "_load_row", lambda hid, msg: (row, msg))
    monkeypatch.setattr(
        refine_mod, "_hydrate", lambda hid, r, final: {"items": [], "reasoning": "ok"}
    )

    client = _client()
    assert (
        client.get(
            f"/feedback/refine/{sign_refine_token(HID, 'swap_shoes')}"
        ).status_code
        == 200
    )
    available[0] = [{"id": "top1"}, {"id": "shoe2"}]  # shoe1 now unavailable
    assert (
        client.get(f"/feedback/refine/{sign_refine_token(HID, 'warmer')}").status_code
        == 200
    )

    assert builds == [HID, HID]  # pool rebuilt on every click
    assert [len(s["turns"]) for s in seen] == [1, 1]  # no accumulated turns
    # The second click's pool reflects the availability change — nothing
    # cached from the first click's conversation.
    assert {i["id"] for i in seen[1]["pool"]} == {"top1", "shoe2"}


# --------------------------------------------------------------------- email


def _outfit(**extra):
    return {
        "label": "Smart casual",
        "reasoning": "clean lines",
        "items": [{"name": "White tee", "photo_url": "http://x/t.jpg"}],
        **extra,
    }


def test_email_renders_refine_links():
    urls = {kind: f"http://x/feedback/refine/tok-{kind}" for kind in REFINE_KINDS}
    html = render_outfit_email(WEATHER, [_outfit(refine_urls=urls)], "Mon")
    for kind in REFINE_KINDS:
        assert f"http://x/feedback/refine/tok-{kind}" in html
    assert "Swap the shoes" in html


def test_email_renders_without_refine_links():
    html = render_outfit_email(WEATHER, [_outfit()], "Mon")
    assert "refine" not in html


# ----------------------------------------------------------------------- job


def test_job_attaches_refine_urls(monkeypatch):
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs"))
    import daily_outfit as job

    monkeypatch.setenv("BACKEND_PUBLIC_URL", "http://x")
    outfits = [{"history_id": HID}, {"no_history": True}]
    job._attach_feedback_links(outfits)
    assert set(outfits[0]["refine_urls"]) == set(REFINE_KINDS)
    for url in outfits[0]["refine_urls"].values():
        assert url.startswith("http://x/feedback/refine/")
    assert "refine_urls" not in outfits[1]
