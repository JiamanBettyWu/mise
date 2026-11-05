"""Tests for the #149 inference-run log — the alive-and-wiped detector.

The heartbeat (preferences_reviewed_at) only catches a run that never
finished. On 2026-07-06 the weekly job finished cleanly, kept nothing, and
removed the two existing inferred prefs; the only trace was a log.warning in
a green Actions run. These tests pin the three things that make that visible:

  1. upsert_node reports how many prior rows it removed (not just written);
  2. run() appends one inference_runs row per completed run, outcome-labelled,
     and the Actions annotation fires only for the wipe case;
  3. GET /profile/inference-runs serves the newest row(s) to the Profile UI.

No Supabase / Claude calls — the graph is driven with fakes.
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import services.preference_inference as pi
from auth import require_password
from routers import profile as profile_router
from services.preference_inference import (
    OUTCOME_EMPTY,
    OUTCOME_INFERRED,
    OUTCOME_INSUFFICIENT,
    classify_outcome,
    empty_wipe_annotation,
    run_row,
    upsert_node,
)

# --- a recording Supabase fake ---------------------------------------------


class _Query:
    """Records the chain and answers every select with canned data."""

    def __init__(self, store, name):
        self.store = store
        self.name = name
        self._op = None

    def select(self, *a, **k):
        self._op = "select"
        return self

    def insert(self, rows):
        self._op = "insert"
        self.store.inserted.append((self.name, rows))
        return self

    def update(self, patch):
        self._op = "update"
        self.store.updated.append((self.name, patch))
        return self

    def delete(self):
        self._op = "delete"
        return self

    def in_(self, col, ids):
        if self._op == "delete":
            self.store.deleted.append((self.name, list(ids)))
        return self

    def eq(self, *a, **k):
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
        self.data = self.store.canned.get((self.name, self._op), [])
        return self


class _FakeSupabase:
    def __init__(self, canned=None):
        self.canned = canned or {}
        self.inserted = []
        self.updated = []
        self.deleted = []

    def table(self, name):
        return _Query(self, name)


# --- 1. upsert_node reports removed -----------------------------------------


def test_upsert_reports_removed_alongside_written(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(pi, "supabase", lambda: fake)

    out = upsert_node({"inferred": [], "prior_inferred_ids": ["p1", "p2"]})

    assert out == {"written": 0, "removed": 2}
    assert fake.inserted == []  # nothing to insert on the wipe path
    assert fake.deleted == [("preferences", ["p1", "p2"])]


def test_upsert_inserts_before_deleting(monkeypatch):
    """Guard the #62 atomicity order while we're here: insert, then delete."""
    calls = []

    class _Ordered(_FakeSupabase):
        def table(self, name):
            q = super().table(name)
            orig_execute = q.execute

            def execute():
                calls.append(q._op)
                return orig_execute()

            q.execute = execute
            return q

    fake = _Ordered()
    monkeypatch.setattr(pi, "supabase", lambda: fake)

    out = upsert_node(
        {
            "inferred": [{"text": "Likes linen", "evidence_ids": ["a", "b", "c"]}],
            "prior_inferred_ids": ["old"],
        }
    )

    assert out == {"written": 1, "removed": 1}
    assert calls == ["insert", "delete"]


# --- 2. run row + outcome + annotation (pure) --------------------------------


@pytest.mark.parametrize(
    "written, outcome",
    [(None, OUTCOME_INSUFFICIENT), (0, OUTCOME_EMPTY), (3, OUTCOME_INFERRED)],
)
def test_classify_outcome(written, outcome):
    assert classify_outcome(written) == outcome


def test_run_row_zeroes_counts_on_insufficient_path():
    # The graph never reaches upsert, so written/removed are absent — the row
    # still carries integers so #146 can sum without null guards.
    row = run_row({"verdicts": 4, "written": None, "removed": None})
    assert row == {
        "outcome": OUTCOME_INSUFFICIENT,
        "verdicts": 4,
        "written": 0,
        "removed": 0,
    }


def test_run_row_for_the_2026_07_06_wipe():
    row = run_row({"verdicts": 26, "written": 0, "removed": 2})
    assert row == {"outcome": OUTCOME_EMPTY, "verdicts": 26, "written": 0, "removed": 2}


def test_annotation_fires_only_for_an_alive_and_wiped_run():
    wiped = {"verdicts": 26, "written": 0, "removed": 2}
    line = empty_wipe_annotation(wiped)
    assert line.startswith("::warning ")  # GitHub workflow command, own line
    assert "removed 2" in line and "26 verdicts" in line
    assert "\n" not in line  # a multi-line body breaks the command

    # "Found nothing, had nothing" is routine; a healthy write is routine; the
    # evidence gate never touched the table. None of these deserve a badge.
    assert empty_wipe_annotation({"verdicts": 12, "written": 0, "removed": 0}) is None
    assert empty_wipe_annotation({"verdicts": 30, "written": 2, "removed": 2}) is None
    assert empty_wipe_annotation({"verdicts": 4, "written": None}) is None


# --- 2b. run() writes the row, then the heartbeat ----------------------------


def test_run_logs_the_wipe_then_stamps_heartbeat(monkeypatch):
    fake = _FakeSupabase(canned={("profile", "select"): [{"id": "prof-1"}]})
    monkeypatch.setattr(pi, "supabase", lambda: fake)

    class _App:
        def invoke(self, _):
            return {
                "verdicts": [{}] * 26,
                "inferred": [],
                "written": 0,
                "removed": 2,
            }

    monkeypatch.setattr(pi, "_APP", _App())

    summary = pi.run()

    assert summary["written"] == 0 and summary["removed"] == 2
    assert fake.inserted == [
        (
            "inference_runs",
            {"outcome": OUTCOME_EMPTY, "verdicts": 26, "written": 0, "removed": 2},
        )
    ]
    # Heartbeat still stamps — the run WAS healthy; the row is what says "wiped".
    assert [t for t, _ in fake.updated] == ["profile"]
    assert "preferences_reviewed_at" in fake.updated[0][1]


def test_run_logs_insufficient_without_touching_prefs(monkeypatch):
    fake = _FakeSupabase(canned={("profile", "select"): [{"id": "prof-1"}]})
    monkeypatch.setattr(pi, "supabase", lambda: fake)

    class _App:
        def invoke(self, _):
            return {"verdicts": [{}] * 3}  # routed to END at check_evidence

    monkeypatch.setattr(pi, "_APP", _App())

    summary = pi.run()

    assert summary["written"] is None  # the job's existing no-op signal
    assert fake.inserted == [
        (
            "inference_runs",
            {
                "outcome": OUTCOME_INSUFFICIENT,
                "verdicts": 3,
                "written": 0,
                "removed": 0,
            },
        )
    ]
    assert fake.deleted == []


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

    class _App:
        def invoke(self, _):
            return {"verdicts": [{}] * 12, "inferred": [], "written": 0, "removed": 0}

    monkeypatch.setattr(pi, "_APP", _App())

    with pytest.raises(RuntimeError):
        pi.run()
    assert fake.updated == []


# --- 3. GET /profile/inference-runs -----------------------------------------


def _client():
    app = FastAPI()
    app.include_router(profile_router.router)
    app.dependency_overrides[require_password] = lambda: None
    return TestClient(app)


_ROW = {
    "id": "11111111-1111-1111-1111-111111111111",
    "ran_at": "2026-07-06T01:24:00+00:00",
    "outcome": "empty",
    "verdicts": 26,
    "written": 0,
    "removed": 2,
}


def test_list_inference_runs_serves_newest_row(monkeypatch):
    fake = _FakeSupabase(canned={("inference_runs", "select"): [_ROW]})
    monkeypatch.setattr(profile_router, "supabase", lambda: fake)

    resp = _client().get("/profile/inference-runs")

    assert resp.status_code == 200
    [row] = resp.json()
    assert row["outcome"] == "empty"
    assert row["removed"] == 2
    assert row["ran_at"].startswith("2026-07-06")


def test_list_inference_runs_empty_before_first_run(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(profile_router, "supabase", lambda: fake)

    resp = _client().get("/profile/inference-runs")

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_inference_runs_limit_is_bounded(monkeypatch):
    fake = _FakeSupabase()
    monkeypatch.setattr(profile_router, "supabase", lambda: fake)

    assert _client().get("/profile/inference-runs?limit=0").status_code == 422
    assert _client().get("/profile/inference-runs?limit=53").status_code == 422
    assert _client().get("/profile/inference-runs?limit=52").status_code == 200
