"""Tests for the recency-decay sampler in services/outfit_history.

Run from repo root:  python backend/test_sampling.py

Pure-Python, no Supabase / Claude calls. Monkey-patches `_recency_scores` so
`sample_wardrobe` can be exercised without a DB.
"""

import random
import sys
from collections import Counter
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services import outfit_history  # noqa: E402
from services.outfit_history import (  # noqa: E402
    DAILY_DECAY,
    _aggregate_scores,
    _weighted_sample_without_replacement,
    sample_wardrobe,
)

TODAY = date(2026, 6, 2)


# --- 1. decay math is correct -------------------------------------------------
rows = [
    {"recommended_on": "2026-06-02", "mode": "Smart casual", "item_ids": ["a"]},
    {"recommended_on": "2026-06-01", "mode": "Smart casual", "item_ids": ["a", "b"]},
    {"recommended_on": "2026-05-28", "mode": "Smart casual", "item_ids": ["b"]},
]
scores = _aggregate_scores(rows, TODAY)
expected_a = 1.0 + DAILY_DECAY
expected_b = DAILY_DECAY + DAILY_DECAY**5
assert abs(scores["a"] - expected_a) < 1e-9, scores
assert abs(scores["b"] - expected_b) < 1e-9, scores
print(f"✓ _aggregate_scores: a={scores['a']:.4f} (today + yesterday), b={scores['b']:.4f}")


# --- 2. weighted sampler: returns exactly k, no duplicates --------------------
items = [{"id": str(i)} for i in range(10)]
sub = _weighted_sample_without_replacement(items, [1.0] * 10, 5)
assert len(sub) == 5
assert len({x["id"] for x in sub}) == 5, "no duplicates"
print("✓ weighted sampler returns k unique items")


# --- 3. weighted sampler: high-weight items chosen far more often -------------
random.seed(42)
two = [{"id": "lucky"}, {"id": "unlucky"}]
hits = Counter()
for _ in range(10_000):
    pick = _weighted_sample_without_replacement(two, [10.0, 0.1], 1)[0]
    hits[pick["id"]] += 1
assert hits["lucky"] > hits["unlucky"] * 20, hits
print(f"✓ weighted sampler biased toward high w: lucky:unlucky = {hits['lucky']}:{hits['unlucky']}")


# --- 4. sample_wardrobe: recently-worn items suppressed -----------------------
fresh = {"id": "fresh"}
worn = {"id": "worn"}
wardrobe = [fresh, worn]


def heavy_worn(modes, today):
    return {"worn": 10.0}


outfit_history._recency_scores = heavy_worn
outfit_history.SAMPLE_FRACTION = 0.5  # keep 1 of 2

random.seed(123)
hits = Counter()
for _ in range(2_000):
    pool = sample_wardrobe(wardrobe, modes=None, today=TODAY)
    assert len(pool) == 1
    hits[pool[0]["id"]] += 1
assert hits["fresh"] > hits["worn"] * 5, hits
print(f"✓ sample_wardrobe suppresses worn items: fresh:worn = {hits['fresh']}:{hits['worn']}")


# --- 5. edge cases ------------------------------------------------------------
assert sample_wardrobe([], modes=None) == []
print("✓ empty wardrobe → empty pool")


def no_recency(modes, today):
    return {}


outfit_history._recency_scores = no_recency
outfit_history.SAMPLE_FRACTION = 0.7

big = [{"id": str(i)} for i in range(100)]
pool = sample_wardrobe(big, modes=None, today=TODAY)
assert len(pool) == 70, f"expected ceil(100*0.7)=70, got {len(pool)}"
print(f"✓ no-history case: sampled exactly {len(pool)}/100")


# --- 6. small wardrobe: sample fraction floors at 1 ---------------------------
tiny = [{"id": "only"}]
pool = sample_wardrobe(tiny, modes=None, today=TODAY)
assert len(pool) == 1
print("✓ 1-item wardrobe → 1-item pool")


print("\nAll sampler tests passed.")
