"""Code-based scorers for the trip-planner eval (#30).

Pure functions over plain dicts: (output, case fields) -> score dict. No weave
imports here — eval_trip.py wraps these as weave ops, and tests/test_eval_scorers.py
covers them offline. A buggy scorer silently corrupts every eval run, so the
metric is tested before the measurement is trusted.

Every scorer returns {"pass": bool, ...details}; scorers that only apply to
some cases also return "applicable" so a vacuous pass is distinguishable from
a real one in the Weave dashboard.

The original #30 sketch had a "covers every day of the trip" check, but the
graph's output groups items by category with no per-day assignment, so there
is nothing to code that check against. Its replacements are
outfit_completeness (a wearable head-to-toe combination exists) and
quantity_for_duration (the top layer scales with trip length).
"""

# A forecast low at/below this is a "cold day" and demands a warm layer.
COLD_LOW_C = 5.0
# Catalog `warmth` is 1..5 (None = not rated); >= 4 counts as a warm layer.
WARM_LAYER_MIN_WARMTH = 4
# The trip needs at least min(duration, TOP_SLOT_CAP) tops-or-dresses; capped
# because re-wearing on longer trips is normal packing advice, not a defect.
TOP_SLOT_CAP = 3

TOP_TYPES = {"shirt", "t-shirt", "blouse", "sweater"}
BOTTOM_TYPES = {"trousers", "jeans", "shorts", "skirt"}
SHOE_TYPES = {"shoes", "boots", "sneakers", "sandals"}
DRESS_TYPES = {"dress"}


def _packed_items(output: dict) -> list[dict]:
    return [
        item
        for category in output.get("packing_list", [])
        for item in category.get("items", [])
    ]


def items_in_catalog(output: dict, catalog: list[dict]) -> dict:
    """Every packed item id must exist in the catalog the graph was given."""
    catalog_ids = {item["id"] for item in catalog}
    unknown = [i["id"] for i in _packed_items(output) if i["id"] not in catalog_ids]
    return {"pass": not unknown, "unknown_ids": unknown}


def outfit_completeness(output: dict) -> dict:
    """A head-to-toe outfit must be packable: (top+bottom or dress) + shoes."""
    types = {(item.get("type") or "").lower() for item in _packed_items(output)}
    has_top = bool(types & TOP_TYPES)
    has_bottom = bool(types & BOTTOM_TYPES)
    has_dress = bool(types & DRESS_TYPES)
    has_shoes = bool(types & SHOE_TYPES)
    return {
        "pass": ((has_top and has_bottom) or has_dress) and has_shoes,
        "has_top": has_top,
        "has_bottom": has_bottom,
        "has_dress": has_dress,
        "has_shoes": has_shoes,
    }


def quantity_for_duration(output: dict, duration_days: int) -> dict:
    """Top-slot items (tops + dresses) must scale with trip length, capped."""
    types = [(item.get("type") or "").lower() for item in _packed_items(output)]
    top_slots = sum(1 for t in types if t in TOP_TYPES | DRESS_TYPES)
    required = min(duration_days, TOP_SLOT_CAP)
    return {"pass": top_slots >= required, "top_slots": top_slots, "required": required}


def cold_requires_warm_layer(output: dict, weather: dict) -> dict:
    """If any forecast day dips to COLD_LOW_C or below, pack a warm layer.

    Only checkable when the injected forecast has daily lows; inferred-climate
    cases (daily=[]) report applicable=False and pass vacuously.
    """
    lows = [day["low_c"] for day in weather.get("daily", [])]
    cold_days = [low for low in lows if low <= COLD_LOW_C]
    if not cold_days:
        return {
            "pass": True,
            "applicable": False,
            "coldest_low_c": min(lows, default=None),
        }
    warm_items = [
        item["id"]
        for item in _packed_items(output)
        if (item.get("warmth") or 0) >= WARM_LAYER_MIN_WARMTH
    ]
    return {
        "pass": bool(warm_items),
        "applicable": True,
        "coldest_low_c": min(cold_days),
        "warm_item_ids": warm_items,
    }


def gaps_surface_as_suggestions(output: dict) -> dict:
    """Every gap from reason_and_select must reach the final output as a
    PurchaseSuggestion (even with results=[]) — the graph's has_gaps branch
    must not drop gaps on the floor. Vacuous when the model found no gaps.
    """
    gap_items = [gap["item"] for gap in output.get("gaps", [])]
    suggested = [sugg["gap"]["item"] for sugg in output.get("purchase_suggestions", [])]
    missing = [g for g in gap_items if g not in suggested]
    return {
        "pass": not missing,
        "applicable": bool(gap_items),
        "gap_count": len(gap_items),
        "suggestion_count": len(suggested),
        "missing": missing,
    }
