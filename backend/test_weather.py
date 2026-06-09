"""Tests for trip weather coverage and climate inference enrichment.

Run from repo root:  python backend/test_weather.py

Pure-Python, no OWM / Claude / Supabase calls. Monkey-patches forecast and
climate helpers so issue #9 behavior can be checked deterministically.
"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from services import trip_planner, weather  # noqa: E402


def _entry(day: date, temp: float, condition: str = "Clouds", pop: float = 0.0):
    dt = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    return {
        "dt": int(dt.timestamp()),
        "main": {"temp": temp},
        "weather": [{"main": condition}],
        "pop": pop,
    }


def _forecast(days: list[date]):
    return {
        "city": {"timezone": 0},
        "list": [
            _entry(d, 20 + i, "Clouds", 0.1)
            for i, d in enumerate(days)
        ],
    }


original_fetch_forecast = weather._fetch_forecast
original_infer_climate_summary = trip_planner.infer_climate_summary
original_parse_json = trip_planner.parse_json
original_client = trip_planner.client

try:
    forecast_days = [
        date(2026, 6, 1),
        date(2026, 6, 2),
        date(2026, 6, 3),
    ]
    weather._fetch_forecast = lambda lat, lon: _forecast(forecast_days)

    # --- 1. full forecast coverage -------------------------------------------
    full = weather.get_weather_for_destination(
        "Paris, France",
        date(2026, 6, 1),
        date(2026, 6, 3),
        lat=48.85,
        lon=2.35,
    )
    assert full.coverage == "full_forecast"
    assert len(full.daily) == 3
    assert full.forecast_summary == full.summary
    assert full.inferred_summary is None
    print("✓ full coverage returns real forecast summary")

    # --- 2. partial forecast coverage ----------------------------------------
    partial = weather.get_weather_for_destination(
        "Paris, France",
        date(2026, 6, 2),
        date(2026, 6, 5),
        lat=48.85,
        lon=2.35,
    )
    assert partial.coverage == "partial_forecast"
    assert [d.date for d in partial.daily] == [date(2026, 6, 2), date(2026, 6, 3)]
    assert partial.forecast_summary
    assert "Forecast covers 2026-06-02 to 2026-06-03" in partial.summary
    print("✓ partial coverage returns available forecast days without crashing")

    # --- 3. no forecast coverage ---------------------------------------------
    missing = weather.get_weather_for_destination(
        "Paris, France",
        date(2026, 6, 10),
        date(2026, 6, 12),
        lat=48.85,
        lon=2.35,
    )
    assert missing.coverage == "inferred_climate"
    assert missing.daily == []
    assert missing.forecast_summary is None
    print("✓ missing coverage returns inference-needed weather without crashing")

    # --- 4. inference node no-ops for full forecast ---------------------------
    out = trip_planner.infer_weather_if_needed_node({"weather": full})
    assert out == {}
    print("✓ inference node no-ops for full forecast")

    # --- 5. inference node enriches partial forecast --------------------------
    trip_planner.infer_climate_summary = (
        lambda state: "Remaining dates are likely warm and humid; this is a climate estimate."
    )
    enriched = trip_planner.infer_weather_if_needed_node(
        {
            "destination": "Paris, France",
            "start_date": date(2026, 6, 2),
            "end_date": date(2026, 6, 5),
            "additional_notes": "",
            "weather": partial,
        }
    )["weather"]
    assert enriched.coverage == "partial_forecast"
    assert enriched.inferred_summary.startswith("Remaining dates")
    assert enriched.forecast_summary in enriched.summary
    assert enriched.inferred_summary in enriched.summary
    print("✓ inference node enriches partial forecast summary")

    # --- 6. inference node enriches fully missing forecast --------------------
    enriched_missing = trip_planner.infer_weather_if_needed_node(
        {
            "destination": "Paris, France",
            "start_date": date(2026, 6, 10),
            "end_date": date(2026, 6, 12),
            "additional_notes": "",
            "weather": missing,
        }
    )["weather"]
    assert enriched_missing.coverage == "inferred_climate"
    assert enriched_missing.forecast_summary is None
    assert enriched_missing.summary == enriched_missing.inferred_summary
    print("✓ inference node enriches missing forecast summary")

    # --- 7. climate parser has a safe missing-key fallback --------------------
    trip_planner.infer_climate_summary = original_infer_climate_summary

    class FakeMessages:
        def create(self, **kwargs):
            return object()

    class FakeClient:
        messages = FakeMessages()

    trip_planner.client = lambda: FakeClient()
    trip_planner.parse_json = lambda resp: {}
    fallback = trip_planner.infer_climate_summary(
        {
            "destination": "Paris, France",
            "start_date": date(2026, 6, 10),
            "end_date": date(2026, 6, 12),
            "additional_notes": "",
            "weather": missing,
        }
    )
    assert fallback.startswith("Climate estimate unavailable")
    print("✓ climate inference tolerates missing inferred_summary key")

finally:
    weather._fetch_forecast = original_fetch_forecast
    trip_planner.infer_climate_summary = original_infer_climate_summary
    trip_planner.parse_json = original_parse_json
    trip_planner.client = original_client


print("\nAll weather tests passed.")
