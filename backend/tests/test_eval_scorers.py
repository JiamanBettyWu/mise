"""Offline tests for the eval scorers + frozen dataset (#30).

evals/scorers.py deliberately imports no weave, so the metric functions are
covered by the free suite — a buggy scorer would silently corrupt every paid
eval run. eval_trip.py itself (weave + live calls) is exercised manually.
"""

import json
from pathlib import Path

from evals import scorers
from schemas import ClothingItem, TripWeather

FIXTURES = json.loads(
    (
        Path(__file__).resolve().parents[1] / "evals" / "datasets" / "trips.json"
    ).read_text()
)

CATALOG = FIXTURES["catalog"]


def _output(items=(), gaps=(), suggestions=()):
    return {
        "packing_list": [{"category": "other", "items": list(items)}],
        "gaps": list(gaps),
        "purchase_suggestions": list(suggestions),
    }


def _item(id="eval-item-0001", type="t-shirt", warmth=1):
    return {"id": id, "type": type, "warmth": warmth}


# ---- dataset validity -------------------------------------------------------


def test_fixture_catalog_rows_are_valid_clothing_items():
    items = [ClothingItem(**row) for row in CATALOG]
    ids = [i.id for i in items]
    assert len(ids) == len(set(ids)), "catalog ids must be unique"
    # The warm-layer check needs at least one qualifying garment to exist,
    # otherwise cold cases could never pass.
    assert any((i.warmth or 0) >= scorers.WARM_LAYER_MIN_WARMTH for i in items)
    # Gap-forcing design: no rain jacket in the frozen catalog.
    assert not any("rain" in i.name.lower() for i in items)


def test_fixture_cases_are_valid():
    for case in FIXTURES["cases"]:
        weather = TripWeather(**case["weather"])
        assert case["start_date"] <= case["end_date"]
        if weather.coverage == "inferred_climate":
            assert weather.daily == []
    case_ids = [c["case_id"] for c in FIXTURES["cases"]]
    assert len(case_ids) == len(set(case_ids))


# ---- items_in_catalog -------------------------------------------------------


def test_items_in_catalog_passes_for_known_ids():
    out = _output(items=[_item("eval-item-0001"), _item("eval-item-0005")])
    assert scorers.items_in_catalog(out, CATALOG) == {"pass": True, "unknown_ids": []}


def test_items_in_catalog_flags_hallucinated_id():
    out = _output(items=[_item("eval-item-0001"), _item("not-a-real-id")])
    res = scorers.items_in_catalog(out, CATALOG)
    assert res["pass"] is False
    assert res["unknown_ids"] == ["not-a-real-id"]


# ---- outfit_completeness ----------------------------------------------------


def test_outfit_complete_with_top_bottom_shoes():
    out = _output(
        items=[_item(type="t-shirt"), _item(type="jeans"), _item(type="sneakers")]
    )
    assert scorers.outfit_completeness(out)["pass"] is True


def test_outfit_complete_with_dress_and_shoes():
    out = _output(items=[_item(type="dress"), _item(type="sandals")])
    assert scorers.outfit_completeness(out)["pass"] is True


def test_outfit_incomplete_without_shoes():
    out = _output(items=[_item(type="t-shirt"), _item(type="jeans")])
    res = scorers.outfit_completeness(out)
    assert res["pass"] is False
    assert res["has_shoes"] is False


def test_outfit_incomplete_with_top_but_no_bottom_or_dress():
    out = _output(items=[_item(type="t-shirt"), _item(type="sneakers")])
    assert scorers.outfit_completeness(out)["pass"] is False


# ---- quantity_for_duration --------------------------------------------------


def test_quantity_scales_with_short_trip():
    out = _output(items=[_item(type="t-shirt"), _item(type="sneakers")])
    assert scorers.quantity_for_duration(out, duration_days=1)["pass"] is True
    assert scorers.quantity_for_duration(out, duration_days=2)["pass"] is False


def test_quantity_requirement_caps_for_long_trips():
    out = _output(
        items=[_item(type="t-shirt"), _item(type="blouse"), _item(type="dress")]
    )
    res = scorers.quantity_for_duration(out, duration_days=10)
    assert res == {"pass": True, "top_slots": 3, "required": scorers.TOP_SLOT_CAP}


# ---- cold_requires_warm_layer -----------------------------------------------

COLD_WEATHER = {"daily": [{"low_c": -4.0}, {"low_c": 2.0}]}
MILD_WEATHER = {"daily": [{"low_c": 12.0}, {"low_c": 9.0}]}


def test_cold_check_passes_with_warm_layer():
    out = _output(items=[_item(type="coat", warmth=5)])
    res = scorers.cold_requires_warm_layer(out, COLD_WEATHER)
    assert res["pass"] is True and res["applicable"] is True
    assert res["coldest_low_c"] == -4.0


def test_cold_check_fails_without_warm_layer():
    out = _output(
        items=[_item(type="t-shirt", warmth=1), _item(type="hat", warmth=None)]
    )
    res = scorers.cold_requires_warm_layer(out, COLD_WEATHER)
    assert res["pass"] is False and res["applicable"] is True


def test_cold_check_vacuous_for_mild_forecast():
    res = scorers.cold_requires_warm_layer(_output(), MILD_WEATHER)
    assert res == {"pass": True, "applicable": False, "coldest_low_c": 9.0}


def test_cold_check_vacuous_for_inferred_climate_without_daily():
    res = scorers.cold_requires_warm_layer(_output(), {"daily": []})
    assert res["pass"] is True and res["applicable"] is False


# ---- gaps_surface_as_suggestions ---------------------------------------------


def test_gaps_check_passes_when_every_gap_has_a_suggestion():
    gap = {"item": "rain jacket", "rationale": "daily rain", "category": "outerwear"}
    out = _output(gaps=[gap], suggestions=[{"gap": gap, "results": []}])
    res = scorers.gaps_surface_as_suggestions(out)
    assert res["pass"] is True and res["applicable"] is True


def test_gaps_check_fails_when_a_gap_is_dropped():
    gap = {"item": "rain jacket", "rationale": "daily rain", "category": "outerwear"}
    res = scorers.gaps_surface_as_suggestions(_output(gaps=[gap]))
    assert res["pass"] is False
    assert res["missing"] == ["rain jacket"]


def test_gaps_check_vacuous_without_gaps():
    res = scorers.gaps_surface_as_suggestions(_output())
    assert res["pass"] is True and res["applicable"] is False
