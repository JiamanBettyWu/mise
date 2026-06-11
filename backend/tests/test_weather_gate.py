"""Tests for the deterministic extremes gate (issue #18).

Pure-Python, no Supabase / Claude calls. The gate must drop only clear
absurdities and stay an identity function everywhere else — wrongly gating a
base layer is the unrecoverable failure mode, so boundaries are tested on
both sides.
"""

from services.weather_gate import COLD_GATE_HIGH_C, HOT_GATE_LOW_C, gate_extremes


def _weather(high, low):
    return {
        "temp_high_c": high,
        "temp_low_c": low,
        "conditions": "clear",
        "precip_chance": 0.0,
        "wind_kmh": 5,
    }


WARDROBE = [
    {"id": "coat", "type": "coat", "warmth": 5},
    {"id": "sweater", "type": "sweater", "warmth": 4},
    {"id": "tee", "type": "t-shirt", "warmth": 1},
    {"id": "sandals", "type": "sandals", "warmth": 1},
    {"id": "boots", "type": "boots", "warmth": 3},
    {"id": "bag", "type": "bag", "warmth": None},
]


def _ids(items):
    return [item["id"] for item in items]


def test_mild_weather_is_identity():
    assert gate_extremes(WARDROBE, _weather(20, 12)) is WARDROBE


def test_heatwave_drops_only_max_warmth():
    pool = gate_extremes(WARDROBE, _weather(35, HOT_GATE_LOW_C))
    assert _ids(pool) == ["sweater", "tee", "sandals", "boots", "bag"]


def test_heat_boundary_below_threshold_keeps_everything():
    assert gate_extremes(WARDROBE, _weather(35, HOT_GATE_LOW_C - 1)) is WARDROBE


def test_deep_cold_drops_only_warmth1_footwear():
    pool = gate_extremes(WARDROBE, _weather(COLD_GATE_HIGH_C, -12))
    # The warmth-1 tee survives: it's a base layer, not an absurdity.
    assert _ids(pool) == ["coat", "sweater", "tee", "boots", "bag"]


def test_cold_boundary_above_threshold_keeps_everything():
    assert gate_extremes(WARDROBE, _weather(COLD_GATE_HIGH_C + 1, -8)) is WARDROBE


def test_null_warmth_never_gated():
    hot = gate_extremes(WARDROBE, _weather(40, 30))
    cold = gate_extremes(WARDROBE, _weather(-10, -20))
    assert "bag" in _ids(hot) and "bag" in _ids(cold)


def test_missing_temps_are_defensive_identity():
    assert gate_extremes(WARDROBE, {"conditions": "clear"}) is WARDROBE


def test_does_not_mutate_input():
    before = list(WARDROBE)
    gate_extremes(WARDROBE, _weather(40, 30))
    assert WARDROBE == before
