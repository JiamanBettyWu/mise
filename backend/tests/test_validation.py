"""Tests for outfit structural validation (issue #46).

Pure-Python, no Supabase / Claude calls. The repair loop is exercised by
monkeypatching `_repair_outfits` in services.claude, same spirit as
test_sampling.py's `_recency_scores` patch.
"""

from services import claude
from services.categories import category_of
from services.validation import drop_extras, validate_outfit

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

WARDROBE = [{"id": iid, "type": t} for iid, t in TYPES.items()]
WEATHER = {
    "temp_high_c": 20,
    "temp_low_c": 12,
    "conditions": "clear",
    "precip_chance": 0.1,
    "wind_kmh": 8,
}


def test_category_map_sanity():
    assert category_of("trousers") == "bottoms"
    assert category_of("Sneakers") == "footwear"  # case-insensitive
    assert category_of("definitely-new-type") == "other"  # unknown types never block


def test_valid_shapes_pass():
    assert validate_outfit(["tee", "jeans", "flats"], TYPES) == []
    assert validate_outfit(["tee", "sweater", "jacket", "jeans", "flats"], TYPES) == []
    assert validate_outfit(["tee", "jeans"], TYPES) == []  # omitted shoes OK (#43)
    assert validate_outfit([], TYPES) == []  # mode-skip case OK


def test_violations_flagged():
    v = validate_outfit(["tee", "jeans", "skirt", "flats"], TYPES)
    assert len(v) == 1 and "bottoms" in v[0], v
    v = validate_outfit(["tee", "jeans", "flats", "sneakers"], TYPES)
    assert len(v) == 1 and "footwear" in v[0], v
    v = validate_outfit(["tee", "tee", "jeans"], TYPES)
    assert any("duplicate" in msg for msg in v), v
    v = validate_outfit(["tee", "ghost-id", "jeans"], TYPES)
    assert any("not in the inventory" in msg for msg in v), v


def test_drop_extras_deterministic_and_valid():
    fixed = drop_extras(["tee", "jeans", "skirt", "flats", "sneakers"], TYPES)
    assert fixed == ["tee", "jeans", "flats"], fixed  # first pick per slot wins
    fixed = drop_extras(["tee", "tee", "ghost-id", "scarf"], TYPES)
    assert fixed == ["tee", "scarf"], fixed
    assert validate_outfit(drop_extras(["jeans", "skirt", "jeans"], TYPES), TYPES) == []


def test_repair_loop_skipped_for_valid_outfits(monkeypatch):
    def _must_not_call(*args, **kwargs):
        raise AssertionError("repair called on valid outfits")

    monkeypatch.setattr(claude, "_repair_outfits", _must_not_call)
    clean = [
        {
            "label": "Smart casual",
            "item_ids": ["tee", "jeans", "flats"],
            "reasoning": "x",
        }
    ]
    out = claude._enforce_structure(clean, WARDROBE, WEATHER, modes=None, notes="")
    assert out == clean


def test_repair_loop_targets_only_failed_outfit(monkeypatch):
    calls = []

    def _good_repair(failed, wardrobe, weather, modes, notes):
        calls.append(len(failed))
        return [
            {
                "label": "Smart casual",
                "item_ids": ["tee", "jeans", "flats"],
                "reasoning": "fixed",
            }
        ]

    monkeypatch.setattr(claude, "_repair_outfits", _good_repair)
    bad = [
        {
            "label": "Smart casual",
            "item_ids": ["tee", "jeans", "skirt", "flats"],
            "reasoning": "x",
        },
        {"label": "Athleisure", "item_ids": ["tee", "sneakers"], "reasoning": "y"},
    ]
    out = claude._enforce_structure(bad, WARDROBE, WEATHER, modes=None, notes="")
    assert calls == [1], calls  # one repair call, only the one failed outfit
    assert out[0]["item_ids"] == ["tee", "jeans", "flats"]
    assert out[1]["item_ids"] == ["tee", "sneakers"]  # untouched


def test_repair_loop_caps_attempts_then_falls_back(monkeypatch):
    calls = []

    def _useless_repair(failed, wardrobe, weather, modes, notes):
        calls.append(len(failed))
        return [None] * len(failed)

    monkeypatch.setattr(claude, "_repair_outfits", _useless_repair)
    stubborn = [
        {
            "label": "Elevated",
            "item_ids": ["skirt", "jeans", "flats", "sneakers"],
            "reasoning": "x",
        }
    ]
    out = claude._enforce_structure(stubborn, WARDROBE, WEATHER, modes=None, notes="")
    assert calls == [1, 1], calls  # exactly MAX_REPAIR_ATTEMPTS calls
    assert out[0]["item_ids"] == [
        "skirt",
        "flats",
    ], out  # extras dropped, first picks kept
    assert validate_outfit(out[0]["item_ids"], TYPES) == []
