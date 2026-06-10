"""Tests for the recency-decay sampler in services/outfit_history.

Pure-Python, no Supabase / Claude calls. `_recency_scores` is monkeypatched
so `sample_wardrobe` can be exercised without a DB.
"""

import random
from collections import Counter
from datetime import date

from services import outfit_history
from services.outfit_history import (
    DAILY_DECAY,
    SMALL_CATEGORY_MAX,
    _aggregate_scores,
    _sampling_weights,
    _weighted_sample_without_replacement,
    sample_wardrobe,
)

TODAY = date(2026, 6, 2)


def test_aggregate_scores_decay_math():
    rows = [
        {"recommended_on": "2026-06-02", "mode": "Smart casual", "item_ids": ["a"]},
        {"recommended_on": "2026-06-01", "mode": "Smart casual", "item_ids": ["a", "b"]},
        {"recommended_on": "2026-05-28", "mode": "Smart casual", "item_ids": ["b"]},
    ]
    scores = _aggregate_scores(rows, TODAY)
    assert abs(scores["a"] - (1.0 + DAILY_DECAY)) < 1e-9, scores
    assert abs(scores["b"] - (DAILY_DECAY + DAILY_DECAY**5)) < 1e-9, scores


def test_weighted_sampler_returns_k_unique_items():
    items = [{"id": str(i)} for i in range(10)]
    sub = _weighted_sample_without_replacement(items, [1.0] * 10, 5)
    assert len(sub) == 5
    assert len({x["id"] for x in sub}) == 5, "no duplicates"


def test_weighted_sampler_biased_toward_high_weight():
    random.seed(42)
    two = [{"id": "lucky"}, {"id": "unlucky"}]
    hits = Counter()
    for _ in range(10_000):
        pick = _weighted_sample_without_replacement(two, [10.0, 0.1], 1)[0]
        hits[pick["id"]] += 1
    assert hits["lucky"] > hits["unlucky"] * 20, hits


def test_sample_wardrobe_suppresses_worn_in_large_category(monkeypatch):
    # 6 tops (> SMALL_CATEGORY_MAX), so recency weighting applies (#44).
    wardrobe = [{"id": f"fresh{i}", "type": "t-shirt"} for i in range(5)]
    wardrobe.append({"id": "worn", "type": "t-shirt"})
    monkeypatch.setattr(
        outfit_history, "_recency_scores", lambda modes, today: {"worn": 10.0}
    )
    monkeypatch.setattr(outfit_history, "SAMPLE_FRACTION", 0.5)  # keep 3 of 6

    random.seed(123)
    hits = Counter()
    for _ in range(2_000):
        pool = sample_wardrobe(wardrobe, modes=None, today=TODAY)
        assert len(pool) == 3
        for item in pool:
            hits[item["id"]] += 1
    assert hits["fresh0"] > hits["worn"] * 3, hits


def test_small_category_exempt_from_recency(monkeypatch):
    # The sandals incident (#44): same heavy "worn" score, but only 2 footwear
    # items (≤ SMALL_CATEGORY_MAX) — rotation pressure is meaningless without
    # substitutes, so both sample evenly.
    sneakers = [{"id": "fresh", "type": "sneakers"}, {"id": "worn", "type": "sneakers"}]
    monkeypatch.setattr(
        outfit_history, "_recency_scores", lambda modes, today: {"worn": 10.0}
    )
    monkeypatch.setattr(outfit_history, "SAMPLE_FRACTION", 0.5)  # keep 1 of 2

    random.seed(123)
    hits = Counter()
    for _ in range(2_000):
        pool = sample_wardrobe(sneakers, modes=None, today=TODAY)
        hits[pool[0]["id"]] += 1
    assert hits["worn"] > hits["fresh"] * 0.8, hits  # ~50/50, not suppressed


def test_exemption_boundary_is_deterministic():
    score_worn = {"worn": 10.0}

    at_max = [{"id": f"s{i}", "type": "shoes"} for i in range(SMALL_CATEGORY_MAX - 1)]
    at_max.append({"id": "worn", "type": "boots"})  # category counts, not type counts
    assert _sampling_weights(at_max, score_worn) == [1.0] * SMALL_CATEGORY_MAX

    over_max = at_max + [{"id": "extra", "type": "sandals"}]
    weights = _sampling_weights(over_max, score_worn)
    assert weights[-2] == 1.0 / 11.0, weights  # worn boots now recency-weighted
    assert all(w == 1.0 for w in weights[:-2] + weights[-1:]), weights


def test_exemption_counts_per_category_not_globally():
    # Mixed wardrobe: 6 tops weighted, 1 shoe exempt despite the same heavy score.
    mixed = [{"id": f"t{i}", "type": "t-shirt"} for i in range(6)]
    mixed.append({"id": "flats", "type": "shoes"})
    weights = _sampling_weights(mixed, {"t0": 10.0, "flats": 10.0})
    assert weights[0] == 1.0 / 11.0 and weights[-1] == 1.0, weights


def test_empty_wardrobe_returns_empty_pool():
    assert sample_wardrobe([], modes=None) == []


def test_no_history_samples_target_fraction(monkeypatch):
    monkeypatch.setattr(outfit_history, "_recency_scores", lambda modes, today: {})
    big = [{"id": str(i)} for i in range(100)]
    pool = sample_wardrobe(big, modes=None, today=TODAY)
    assert len(pool) == 70, f"expected ceil(100*0.7)=70, got {len(pool)}"


def test_single_item_wardrobe(monkeypatch):
    monkeypatch.setattr(outfit_history, "_recency_scores", lambda modes, today: {})
    pool = sample_wardrobe([{"id": "only"}], modes=None, today=TODAY)
    assert len(pool) == 1
