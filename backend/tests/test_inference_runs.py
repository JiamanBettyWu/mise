"""Tests for the #149 inference-run log — the alive-and-wiped detector.

The heartbeat (preferences_reviewed_at) only catches a run that never
finished. On 2026-07-06 the weekly job finished cleanly, kept nothing, and
removed the two existing inferred prefs; the only trace was a log.warning in
a green Actions run. These tests pin the things that make that visible:

  1. upsert_node labels its outcome explicitly and reports the prior-set size;
  2. run() resolves an outcome (raising on an unlabelled finish), appends one
     inference_runs row BEFORE the heartbeat, and the Actions annotation
     fires only for the wipe case;
  3. GET /profile carries the newest run and the newest wipe, so the Profile
     UI can explain an empty section without an extra round-trip.

No Supabase / Claude calls — the graph is driven with fakes.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.preference_inference as pi
from auth import require_password
from routers import profile as profile_router
from services.preference_inference import (
    MIN_VERDICTS,
    OUTCOME_EMPTY,
    OUTCOME_INFERRED,
    OUTCOME_INSUFFICIENT,
    empty_wipe_annotation,
    resolve_outcome,
    run_row,
    upsert_node,
)

# --- a recording Supabase fake ---------------------------------------------


class _Query:
    """Records every executed (table, op) in one shared ordered log, and
    answers selects with canned data keyed by (table, op) or by a filter."""

    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._op = None
        self._filters = []
        self._payload = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, rows):
        self._op = "insert"
        self._payload = rows
        return self

    def update(self, patch):
        self._op = "update"
        self._payload = patch
        return self

    def delete(self):
        self._op = "delete"
        return self

    def in_(self, col, ids):
        if self._op == "delete":
            self._payload = list(ids)
        return self

    def eq(self, col, val):
        self._filters.append((col, val))
        return self

    def gt(self, col, val):
        self._filters.append((col, f">{val}"))
        return self

    def not_(self):
        return self

    def is_(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def execute(self):
        self.store.calls.append((self.name, self._op, self._payload))
        key = (self.name, self._op, tuple(self._filters))
        self.data = self.store.canned.get(
            key, self.store.canned.get((self.name, self._op), [])
        )
        return self


class _FakeSupabase:
    def __init__(self, canned=None):
        self.canned = canned or {}
        self.calls = []  # (table, op, payload), in execution order

    def table(self, name):
        return _Query(self, name)

    def ops(self, table=None):
        return [(t, op) for t, op, _ in self.calls if table is None or t == table]


# --- 1. upsert_node: explicit outcome + prior-set size ----------------------


def test_upsert_labels_the_wipe_and_reports_prior_set_size(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(pi, "supabase", lambda: fake)

    out = upsert_node({"inferred": [], "prior_inferred_ids": ["p1", "p2"]})

    assert out == {"written": 0, "removed": 2, "outcome": OUTCOME_EMPTY}
    assert fake.ops() == [("preferences", "delete")]  # nothing to insert
    assert fake.calls[0][2] == ["p1", "p2"]


def test_upsert_inserts_before_deleting_and_labels_inferred(monkeypatch):
    """Guard the #62 atomicity order while we're here: insert, then delete."""
    fake = _FakeSupabase()
    monkeypatch.setattr(pi, "supabase", lambda: fake)

    out = upsert_node(
        {
            "inferred": [{"text": "Likes linen", "evidence_ids": ["a", "b", "c"]}],
            "prior_inferred_ids": ["old"],
        }
    )

    assert out == {"written": 1, "removed": 1, "outcome": OUTCOME_INFERRED}
    assert fake.ops() == [("preferences", "insert"), ("preferences", "delete")]


# --- 2. outcome resolution, run row, annotation (pure) ----------------------


def test_resolve_outcome_trusts_the_explicit_label():
    assert (
        resolve_outcome({"outcome": OUTCOME_EMPTY, "verdicts": [{}] * 26})
        == OUTCOME_EMPTY
    )
    assert (
        resolve_outcome({"outcome": OUTCOME_INFERRED, "verdicts": []})
        == OUTCOME_INFERRED
    )


def test_resolve_outcome_insufficient_only_below_the_gate():
    assert (
        resolve_outcome({"verdicts": [{}] * (MIN_VERDICTS - 1)}) == OUTCOME_INSUFFICIENT
    )
    assert resolve_outcome({}) == OUTCOME_INSUFFICIENT


def test_resolve_outcome_refuses_an_unlabelled_finish_on_enough_evidence():
    """A future node that returns early without labelling itself must go red,
    not get logged as 'insufficient' and have the UI say 'not enough rated
    outfits' on 26 verdicts."""
    with pytest.raises(RuntimeError, match="without a recognised outcome"):
        resolve_outcome({"verdicts": [{}] * MIN_VERDICTS})
    with pytest.raises(RuntimeError):
        resolve_outcome({"outcome": "bogus", "verdicts": []})


def test_run_row_zeroes_counts_on_insufficient_path():
    # The graph never reaches upsert, so written/removed are absent — the row
    # still carries integers so #146 can sum without null guards.
    row = run_row({"outcome": OUTCOME_INSUFFICIENT, "verdicts": 4, "written": None})
    assert row == {
        "outcome": OUTCOME_INSUFFICIENT,
        "verdicts": 4,
        "written": 0,
        "removed": 0,
    }


def test_run_row_for_the_2026_07_06_wipe():
    row = run_row(
        {"outcome": OUTCOME_EMPTY, "verdicts": 26, "written": 0, "removed": 2}
    )
    assert row == {"outcome": OUTCOME_EMPTY, "verdicts": 26, "written": 0, "removed": 2}


def test_annotation_fires_only_for_an_alive_and_wiped_run():
    wiped = {"outcome": OUTCOME_EMPTY, "verdicts": 26, "written": 0, "removed": 2}
    line = empty_wipe_annotation(wiped)
    assert line.startswith("::warning ")  # GitHub workflow command, own line
    assert "removed 2" in line and "26 verdicts" in line
    assert "\n" not in line  # a multi-line body breaks the command

    # "Found nothing, had nothing" is routine; a healthy write is routine; the
    # evidence gate never touched the table. None of these deserve a badge.
    assert (
        empty_wipe_annotation(
            {"outcome": OUTCOME_EMPTY, "verdicts": 12, "written": 0, "removed": 0}
        )
        is None
    )
    assert (
        empty_wipe_annotation(
            {"outcome": OUTCOME_INFERRED, "verdicts": 30, "written": 2, "removed": 2}
        )
        is None
    )
    assert (
        empty_wipe_annotation({"outcome": OUTCOME_INSUFFICIENT, "verdicts": 4}) is None
    )


# --- 2b. run() writes the row, THEN the heartbeat ----------------------------


def _app_returning(final):
    class _App:
        def invoke(self, _):
            return final

    return _App()


def test_run_logs_the_wipe_then_stamps_heartbeat(monkeypatch):
    fake = _FakeSupabase(canned={("profile", "select"): [{"id": "prof-1"}]})
    monkeypatch.setattr(pi, "supabase", lambda: fake)
    monkeypatch.setattr(
        pi,
        "_APP",
        _app_returning(
            {
                "verdicts": [{}] * 26,
                "inferred": [],
                "written": 0,
                "removed": 2,
                "outcome": OUTCOME_EMPTY,
            }
        ),
    )

    summary = pi.run()

    assert summary["outcome"] == OUTCOME_EMPTY
    assert summary["written"] == 0 and summary["removed"] == 2
    # One shared ordered log: the run row lands BEFORE the heartbeat stamp, so
    # a failed insert can never leave a fresh heartbeat behind it.
    assert fake.ops() == [
        ("inference_runs", "insert"),
        ("profile", "select"),
        ("profile", "update"),
    ]
    assert fake.calls[0][2] == {
        "outcome": OUTCOME_EMPTY,
        "verdicts": 26,
        "written": 0,
        "removed": 2,
    }
    assert "preferences_reviewed_at" in fake.calls[2][2]


def test_run_logs_insufficient_without_touching_prefs(monkeypatch):
    fake = _FakeSupabase(canned={("profile", "select"): [{"id": "prof-1"}]})
    monkeypatch.setattr(pi, "supabase", lambda: fake)
    monkeypatch.setattr(pi, "_APP", _app_returning({"verdicts": [{}] * 3}))

    summary = pi.run()

    assert summary["outcome"] == OUTCOME_INSUFFICIENT
    assert summary["written"] is None  # the job's existing no-op signal
    assert fake.ops("inference_runs") == [("inference_runs", "insert")]
    assert fake.calls[0][2] == {
        "outcome": OUTCOME_INSUFFICIENT,
        "verdicts": 3,
        "written": 0,
        "removed": 0,
    }
    assert fake.ops("preferences") == []


def test_run_row_insert_failure_leaves_heartbeat_stale(monkeypatch):
    """A missing run record must not masquerade as a healthy run: the insert
    raises, the job exits nonzero, and the heartbeat is never stamped."""
    fake = _FakeSupabase()

    class _Boom(_Query):
        def execute(self):
            if self.name == "inference_runs":
                raise RuntimeError("supabase down")
            return super().execute()

    fake.table = lambda name: _Boom(fake, name)
    monkeypatch.setattr(pi, "supabase", lambda: fake)
    monkeypatch.setattr(
        pi,
        "_APP",
        _app_returning(
            {
                "verdicts": [{}] * 12,
                "inferred": [],
                "written": 0,
                "removed": 0,
                "outcome": OUTCOME_EMPTY,
            }
        ),
    )

    with pytest.raises(RuntimeError):
        pi.run()
    assert fake.ops("profile") == []


def test_run_refuses_to_log_an_unlabelled_finish(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(pi, "supabase", lambda: fake)
    monkeypatch.setattr(pi, "_APP", _app_returning({"verdicts": [{}] * 26}))

    with pytest.raises(RuntimeError):
        pi.run()
    assert fake.calls == []  # neither the row nor the heartbeat


# --- 3. GET /profile carries the newest run + newest wipe -------------------


def _client():
    app = FastAPI()
    app.include_router(profile_router.router)
    app.dependency_overrides[require_password] = lambda: None
    return TestClient(app)


_WIPE = {
    "id": "11111111-1111-1111-1111-111111111111",
    "ran_at": "2026-07-06T01:24:00+00:00",
    "outcome": "empty",
    "verdicts": 26,
    "written": 0,
    "removed": 2,
}
_LATER = {
    "id": "22222222-2222-2222-2222-222222222222",
    "ran_at": "2026-07-13T01:24:00+00:00",
    "outcome": "empty",
    "verdicts": 28,
    "written": 0,
    "removed": 0,
}
_PROFILE = {"id": "prof-1", "preferences_reviewed_at": "2026-07-13T01:24:05+00:00"}


def test_get_profile_carries_newest_run_and_newest_wipe(monkeypatch):
    # Newest run is the routine Jul 13 "wrote 0, removed 0"; the wipe query
    # (outcome=empty, removed>0) still surfaces Jul 6 so the UI can say so.
    fake = _FakeSupabase(
        canned={
            ("profile", "select"): [_PROFILE],
            ("inference_runs", "select", ()): [_LATER],
            ("inference_runs", "select", (("outcome", "empty"), ("removed", ">0"))): [
                _WIPE
            ],
        }
    )
    monkeypatch.setattr(profile_router, "supabase", lambda: fake)

    resp = _client().get("/profile")

    assert resp.status_code == 200
    body = resp.json()
    assert body["preferences_reviewed_at"].startswith("2026-07-13")
    assert body["last_inference_run"]["id"] == _LATER["id"]
    assert body["last_inference_wipe"]["id"] == _WIPE["id"]
    assert body["last_inference_wipe"]["removed"] == 2


def test_get_profile_before_any_run(monkeypatch):
    fake = _FakeSupabase(canned={("profile", "select"): [_PROFILE]})
    monkeypatch.setattr(profile_router, "supabase", lambda: fake)

    body = _client().get("/profile").json()

    assert body["last_inference_run"] is None
    assert body["last_inference_wipe"] is None


def test_get_profile_with_no_profile_row_still_answers(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(profile_router, "supabase", lambda: fake)

    resp = _client().get("/profile")

    assert resp.status_code == 200
    assert resp.json()["last_inference_run"] is None
