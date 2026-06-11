"""Tests for the recency-decay sampler in services/outfit_history.

Pure-Python, no Supabase / Claude calls. The two DB fetches (`_recency_scores`,
`_feedback_rows`) are monkeypatched so `sample_wardrobe` can be exercised
without a DB.
"""

import random
from collections import Counter
from datetime import date

import pytest

from services import outfit_history
from services.outfit_history import (
    DAILY_DECAY,
    FEEDBACK_CEILING,
    FEEDBACK_FLOOR,
    SMALL_CATEGORY_MAX,
    _aggregate_scores,
    _feedback_multipliers,
    _sampling_weights,
    _weighted_sample_without_replacement,
    sample_wardrobe,
)

TODAY = date(2026, 6, 2)


@pytest.fixture
def no_feedback(monkeypatch):
    monkeypatch.setattr(outfit_history, "_feedback_rows", lambda: [])


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


def test_sample_wardrobe_suppresses_worn_in_large_category(monkeypatch, no_feedback):
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


def test_small_category_exempt_from_recency(monkeypatch, no_feedback):
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
    assert _sampling_weights(at_max, score_worn, {}) == [1.0] * SMALL_CATEGORY_MAX

    over_max = at_max + [{"id": "extra", "type": "sandals"}]
    weights = _sampling_weights(over_max, score_worn, {})
    assert weights[-2] == 1.0 / 11.0, weights  # worn boots now recency-weighted
    assert all(w == 1.0 for w in weights[:-2] + weights[-1:]), weights


def test_exemption_counts_per_category_not_globally():
    # Mixed wardrobe: 6 tops weighted, 1 shoe exempt despite the same heavy score.
    mixed = [{"id": f"t{i}", "type": "t-shirt"} for i in range(6)]
    mixed.append({"id": "flats", "type": "shoes"})
    weights = _sampling_weights(mixed, {"t0": 10.0, "flats": 10.0}, {})
    assert weights[0] == 1.0 / 11.0 and weights[-1] == 1.0, weights


def test_empty_wardrobe_returns_empty_pool():
    assert sample_wardrobe([], modes=None) == []


def test_no_history_samples_target_fraction(monkeypatch, no_feedback):
    monkeypatch.setattr(outfit_history, "_recency_scores", lambda modes, today: {})
    big = [{"id": str(i)} for i in range(100)]
    pool = sample_wardrobe(big, modes=None, today=TODAY)
    assert len(pool) == 70, f"expected ceil(100*0.7)=70, got {len(pool)}"


def test_single_item_wardrobe(monkeypatch, no_feedback):
    monkeypatch.setattr(outfit_history, "_recency_scores", lambda modes, today: {})
    pool = sample_wardrobe([{"id": "only"}], modes=None, today=TODAY)
    assert len(pool) == 1


# --- Feedback multiplier (#42) ---


def test_feedback_multipliers_worked_examples():
    # One 👎 on a 3-item outfit: each item gets 1/3 blame →
    # score = 1 / (1/3 + 2) = 3/7, mult = 0.6 + 0.8 × 3/7 ≈ 0.943 (D2).
    rows = [{"item_ids": ["a", "b", "c"], "feedback": -1}]
    mults = _feedback_multipliers(rows)
    expected = FEEDBACK_FLOOR + (FEEDBACK_CEILING - FEEDBACK_FLOOR) * (3 / 7)
    assert all(abs(mults[i] - expected) < 1e-9 for i in "abc"), mults

    # The innocent blazer in three liked 3-item outfits: ups = 1.0 →
    # score = 2/3, mult ≈ 1.13.
    rows = [{"item_ids": ["blazer", f"x{i}", f"y{i}"], "feedback": 1} for i in range(3)]
    mults = _feedback_multipliers(rows)
    expected = FEEDBACK_FLOOR + (FEEDBACK_CEILING - FEEDBACK_FLOOR) * (2 / 3)
    assert abs(mults["blazer"] - expected) < 1e-9, mults


def test_feedback_multipliers_stay_within_bounds():
    # 50 solo thumbs-downs / thumbs-ups: asymptotically approaches the
    # clamp but never crosses it — the bounds come from the formula itself.
    downs = [{"item_ids": ["hated"], "feedback": -1}] * 50
    ups = [{"item_ids": ["loved"], "feedback": 1}] * 50
    mults = _feedback_multipliers(downs + ups)
    assert FEEDBACK_FLOOR < mults["hated"] < 0.62, mults
    assert 1.38 < mults["loved"] < FEEDBACK_CEILING, mults


def test_feedback_ignores_unrated_and_malformed_rows():
    rows = [
        {"item_ids": ["a"], "feedback": None},
        {"item_ids": ["a"], "feedback": 0},
        {"item_ids": [], "feedback": 1},
        {"item_ids": None, "feedback": -1},
    ]
    assert _feedback_multipliers(rows) == {}


def test_feedback_applies_even_in_small_categories():
    # The #44 exemption lifts rotation pressure, not preference: a disliked
    # item in a 2-item category still gets its feedback multiplier.
    sneakers = [{"id": "liked", "type": "sneakers"}, {"id": "meh", "type": "sneakers"}]
    weights = _sampling_weights(sneakers, {"meh": 10.0}, {"meh": 0.8})
    assert weights == [1.0, 0.8], weights  # recency exempt, feedback not


def test_feedback_composes_with_recency():
    # Large category: w = 1/(1+score) × mult.
    tops = [{"id": f"t{i}", "type": "t-shirt"} for i in range(6)]
    weights = _sampling_weights(tops, {"t0": 1.0}, {"t0": 1.4})
    assert abs(weights[0] - 0.5 * 1.4) < 1e-9, weights
    assert all(w == 1.0 for w in weights[1:]), weights


def test_sample_wardrobe_downweights_disliked(monkeypatch):
    # End-to-end through sample_wardrobe: a consistently disliked top is
    # sampled less often, but (floor!) never vanishes.
    wardrobe = [{"id": f"t{i}", "type": "t-shirt"} for i in range(5)]
    wardrobe.append({"id": "hated", "type": "t-shirt"})
    monkeypatch.setattr(outfit_history, "_recency_scores", lambda modes, today: {})
    monkeypatch.setattr(
        outfit_history,
        "_feedback_rows",
        lambda: [{"item_ids": ["hated"], "feedback": -1}] * 50,
    )
    monkeypatch.setattr(outfit_history, "SAMPLE_FRACTION", 0.5)  # keep 3 of 6

    random.seed(7)
    hits = Counter()
    for _ in range(2_000):
        for item in sample_wardrobe(wardrobe, modes=None, today=TODAY):
            hits[item["id"]] += 1
    assert hits["hated"] > 0, "floor keeps disliked items auditioning"
    assert hits["t0"] > hits["hated"] * 1.2, hits
