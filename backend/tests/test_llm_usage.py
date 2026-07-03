"""Tests for the llm_usage metering funnel (#114).

Covers the three postures of create_tracked: a normal call inserts one row
with the usage split, a response without usage (test fakes) records nothing,
and a failed insert never propagates — metering must not break the product
call it wraps.
"""

import pytest

import services.claude as claude


class _FakeUsage:
    input_tokens = 11
    output_tokens = 22
    cache_creation_input_tokens = 33
    cache_read_input_tokens = None  # API omits it on cacheless calls


class _FakeResp:
    usage = _FakeUsage()


class _FakeAnthropicClient:
    def __init__(self, resp):
        self._resp = resp
        self.last_kwargs = None
        self.messages = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return self._resp


class _FakeTable:
    def __init__(self, fail=False):
        self.fail = fail
        self.inserted = []

    def table(self, name):
        assert name == "llm_usage"
        return self

    def insert(self, row):
        self.inserted.append(row)
        return self

    def execute(self):
        if self.fail:
            raise RuntimeError("supabase down")


@pytest.fixture
def tracked(monkeypatch):
    def _install(resp, fail_insert=False):
        anthropic = _FakeAnthropicClient(resp)
        table = _FakeTable(fail=fail_insert)
        monkeypatch.setattr(claude, "client", lambda: anthropic)
        monkeypatch.setattr(claude, "supabase", lambda: table)
        return anthropic, table

    return _install


def test_create_tracked_inserts_usage_row(tracked):
    anthropic, table = tracked(_FakeResp())
    resp = claude.create_tracked("daily_outfit", model="m1", max_tokens=5)
    assert resp is anthropic._resp
    assert anthropic.last_kwargs == {"model": "m1", "max_tokens": 5}
    assert table.inserted == [
        {
            "call_type": "daily_outfit",
            "model": "m1",
            "input_tokens": 11,
            "output_tokens": 22,
            "cache_creation_input_tokens": 33,
            "cache_read_input_tokens": 0,
        }
    ]


def test_create_tracked_skips_usageless_response(tracked):
    _, table = tracked(object())
    claude.create_tracked("repair", model="m1")
    assert table.inserted == []


def test_create_tracked_survives_insert_failure(tracked):
    anthropic, _ = tracked(_FakeResp(), fail_insert=True)
    resp = claude.create_tracked("trip_plan", model="m1")
    assert resp is anthropic._resp  # the product call still succeeds
