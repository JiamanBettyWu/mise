"""Tests for outfit structural validation (issue #46).

Run from repo root:  python backend/test_validation.py

Pure-Python, no Supabase / Claude calls. The repair loop is exercised by
monkey-patching `_repair_outfits` in services.claude, same spirit as
test_sampling.py's `_recency_scores` patch.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services import claude  # noqa: E402
from services.categories import category_of  # noqa: E402
from services.validation import drop_extras, validate_outfit  # noqa: E402

TYPES = {
    "tee": "t-shirt",
    "sweater": "sweater",
    "jacket": "jacket",
    "jeans": "jeans",
    "skirt": "skirt",
    "flats": "shoes",
    "sneakers": "sneakers",
    "scarf": "scarf",
}


# --- 1. category map sanity ----------------------------------------------------
assert category_of("trousers") == "bottoms"
assert category_of("Sneakers") == "footwear"  # case-insensitive
assert category_of("definitely-new-type") == "other"  # unknown types never block
print("✓ category_of: bottoms/footwear mapped, unknown → other")


# --- 2. validate_outfit: valid shapes pass -------------------------------------
assert validate_outfit(["tee", "jeans", "flats"], TYPES) == []
assert validate_outfit(["tee", "sweater", "jacket", "jeans", "flats"], TYPES) == []
assert validate_outfit(["tee", "jeans"], TYPES) == []  # omitted shoes OK (#43)
assert validate_outfit([], TYPES) == []  # mode-skip case OK
print("✓ validate_outfit: layered tops, omitted slots, and skips all pass")


# --- 3. validate_outfit: violations flagged ------------------------------------
v = validate_outfit(["tee", "jeans", "skirt", "flats"], TYPES)
assert len(v) == 1 and "bottoms" in v[0], v
v = validate_outfit(["tee", "jeans", "flats", "sneakers"], TYPES)
assert len(v) == 1 and "footwear" in v[0], v
v = validate_outfit(["tee", "tee", "jeans"], TYPES)
assert any("duplicate" in msg for msg in v), v
v = validate_outfit(["tee", "ghost-id", "jeans"], TYPES)
assert any("not in the inventory" in msg for msg in v), v
print("✓ validate_outfit: two bottoms, two footwear, dupes, unknown ids flagged")


# --- 4. drop_extras: deterministic, order-preserving, always valid --------------
fixed = drop_extras(["tee", "jeans", "skirt", "flats", "sneakers"], TYPES)
assert fixed == ["tee", "jeans", "flats"], fixed  # first pick per slot wins
fixed = drop_extras(["tee", "tee", "ghost-id", "scarf"], TYPES)
assert fixed == ["tee", "scarf"], fixed
assert validate_outfit(drop_extras(["jeans", "skirt", "jeans"], TYPES), TYPES) == []
print("✓ drop_extras: keeps first per slot, drops dupes/unknowns, output validates")


# --- 5. repair loop: clean outfits never trigger a model call -------------------
WARDROBE = [{"id": iid, "type": t} for iid, t in TYPES.items()]
WEATHER = {
    "temp_high_c": 20,
    "temp_low_c": 12,
    "conditions": "clear",
    "precip_chance": 0.1,
    "wind_kmh": 8,
}


def _must_not_call(*args, **kwargs):
    raise AssertionError("repair called on valid outfits")


claude._repair_outfits = _must_not_call
clean = [{"label": "Smart casual", "item_ids": ["tee", "jeans", "flats"], "reasoning": "x"}]
out = claude._enforce_structure(clean, WARDROBE, WEATHER, modes=None, notes="")
assert out == clean
print("✓ repair loop: valid outfits pass through with zero extra calls")


# --- 6. repair loop: a good repair is accepted on attempt 1 ---------------------
calls = []


def _good_repair(failed, wardrobe, weather, modes, notes):
    calls.append(len(failed))
    return [{"label": "Smart casual", "item_ids": ["tee", "jeans", "flats"], "reasoning": "fixed"}]


claude._repair_outfits = _good_repair
bad = [
    {"label": "Smart casual", "item_ids": ["tee", "jeans", "skirt", "flats"], "reasoning": "x"},
    {"label": "Athleisure", "item_ids": ["tee", "sneakers"], "reasoning": "y"},
]
out = claude._enforce_structure(bad, WARDROBE, WEATHER, modes=None, notes="")
assert calls == [1], calls  # one repair call, only the one failed outfit
assert out[0]["item_ids"] == ["tee", "jeans", "flats"]
assert out[1]["item_ids"] == ["tee", "sneakers"]  # untouched
print("✓ repair loop: targeted repair fixes only the failed outfit")


# --- 7. repair loop: stubborn failure → capped attempts, then fallback ----------
calls = []


def _useless_repair(failed, wardrobe, weather, modes, notes):
    calls.append(len(failed))
    return [None] * len(failed)


claude._repair_outfits = _useless_repair
stubborn = [
    {"label": "Elevated", "item_ids": ["skirt", "jeans", "flats", "sneakers"], "reasoning": "x"}
]
out = claude._enforce_structure(stubborn, WARDROBE, WEATHER, modes=None, notes="")
assert calls == [1, 1], calls  # exactly MAX_REPAIR_ATTEMPTS calls
assert out[0]["item_ids"] == ["skirt", "flats"], out  # extras dropped, first picks kept
assert validate_outfit(out[0]["item_ids"], TYPES) == []
print("✓ repair loop: 2 capped attempts, then deterministic fallback validates")


print("\nAll validation tests passed.")
