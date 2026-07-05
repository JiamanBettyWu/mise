"""Tests for the #128 saved-trip-plans CRUD.

Thin pass-through endpoints — the one contract worth pinning offline is that
GET /trips (the list) never pulls the jsonb `plan` blob, since that's the
whole point of TripPlanSummary existing as a separate, smaller schema from
TripPlanSaved. The real logic (client-side pruning, live-catalog packed
cross-ref) is frontend and verified in-browser.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from auth import require_password
from routers import trips as trips_router


class _FakeQuery:
    def __init__(self):
        self.select_cols = None
        self.data = []

    def select(self, cols):
        self.select_cols = cols
        return self

    def order(self, *a, **k):
        return self

    def eq(self, *a, **k):
        return self

    def execute(self):
        return self


class _FakeTable:
    def __init__(self, capture):
        self.capture = capture

    def select(self, cols):
        self.capture.append(cols)
        return _FakeQuery().select(cols)


class _FakeClient:
    def __init__(self):
        self.selects = []

    def table(self, name):
        assert name == "trip_plans"
        return _FakeTable(self.selects)


def _client():
    app = FastAPI()
    app.include_router(trips_router.router)
    app.dependency_overrides[require_password] = lambda: None
    return TestClient(app)


def test_list_trips_never_selects_the_plan_column(monkeypatch):
    fake = _FakeClient()
    monkeypatch.setattr(trips_router, "supabase", lambda: fake)

    resp = _client().get("/trips")

    assert resp.status_code == 200
    assert fake.selects, "list_trips never called select()"
    assert "plan" not in fake.selects[0]
    assert fake.selects[0] == "id,created_at,destination,start_date,end_date,notes,edited"
