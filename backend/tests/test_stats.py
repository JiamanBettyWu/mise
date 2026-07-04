"""Tests for the #115 profile-stats aggregation (services/stats.py).

Pure-Python — the endpoint's Supabase queries are thin; the money math and
the counting are what can silently go wrong, so that's what's pinned here.
"""

from datetime import datetime, timezone

import pytest

from services.stats import (
    aggregate_outfits,
    aggregate_usage,
    range_cutoff,
    row_cost,
)

# --- row_cost: derived dollars must respect the cache columns -------------


def test_cost_uses_all_four_token_columns():
    # 1M of each token class on Sonnet 4.6: 3.00 + 3.75 + 0.30 + 15.00
    row = {
        "model": "claude-sonnet-4-6",
        "input_tokens": 1_000_000,
        "cache_creation_input_tokens": 1_000_000,
        "cache_read_input_tokens": 1_000_000,
        "output_tokens": 1_000_000,
    }
    assert row_cost(row) == pytest.approx(22.05)


def test_cost_matches_dated_haiku_snapshot_by_prefix():
    row = {
        "model": "claude-haiku-4-5-20251001",
        "input_tokens": 2_000_000,
        "output_tokens": 1_000_000,
        "cache_creation_input_tokens": 0,
        "cache_read_input_tokens": 0,
    }
    assert row_cost(row) == pytest.approx(7.00)  # 2*1.00 + 1*5.00


def test_unknown_model_returns_none():
    assert row_cost({"model": "gpt-oops", "input_tokens": 100}) is None


# --- aggregate_usage -------------------------------------------------------


def test_aggregate_groups_by_call_type_and_flags_unpriced():
    rows = [
        {
            "call_type": "daily_outfit",
            "model": "claude-sonnet-4-6",
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        {
            "call_type": "daily_outfit",
            "model": "claude-sonnet-4-6",
            "input_tokens": 100,
            "output_tokens": 50,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
        {
            "call_type": "mode_classify",
            "model": "some-future-model",
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_creation_input_tokens": 0,
            "cache_read_input_tokens": 0,
        },
    ]
    agg = aggregate_usage(rows)
    assert agg["by_call_type"]["daily_outfit"]["calls"] == 2
    assert agg["by_call_type"]["daily_outfit"]["tokens"] == 300
    assert agg["total_calls"] == 3
    assert agg["total_tokens"] == 315
    assert agg["has_unpriced"] is True  # unpriced counts tokens, not dollars
    assert agg["total_cost"] == pytest.approx(2 * (100 * 3 + 50 * 15) / 1e6)


def test_aggregate_empty():
    agg = aggregate_usage([])
    assert agg["total_calls"] == 0
    assert agg["total_tokens"] == 0
    assert agg["total_cost"] == 0
    assert agg["by_call_type"] == {}
    assert agg["has_unpriced"] is False


# --- aggregate_outfits ------------------------------------------------------


def test_outfit_counts_feedback_and_thumbs_rate():
    rows = [
        {"item_ids": ["a", "b"], "feedback": 1},
        {"item_ids": ["a"], "feedback": -1},
        {"item_ids": ["a", "c"], "feedback": None},
    ]
    agg = aggregate_outfits(rows)
    assert agg["outfits"] == 3
    assert agg["feedback_count"] == 2
    assert agg["thumbs_up_rate"] == 0.5
    assert agg["top_item_counts"][0] == ("a", 3)


def test_outfit_no_feedback_rate_is_none():
    agg = aggregate_outfits([{"item_ids": [], "feedback": None}])
    assert agg["thumbs_up_rate"] is None


def test_top_items_capped_at_five_stable_order():
    rows = [{"item_ids": [c], "feedback": None} for c in "abcdefg"]
    agg = aggregate_outfits(rows)
    assert len(agg["top_item_counts"]) == 5
    # all counts tie at 1 → deterministic id order
    assert [i for i, _ in agg["top_item_counts"]] == ["a", "b", "c", "d", "e"]


# --- range_cutoff ------------------------------------------------------------


def test_range_cutoff_days_and_all():
    now = datetime(2026, 7, 3, tzinfo=timezone.utc)
    assert range_cutoff("7d", now) == "2026-06-26T00:00:00+00:00"
    assert range_cutoff("all", now) is None
