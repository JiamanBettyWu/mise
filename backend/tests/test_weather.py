"""Tests for trip weather coverage and climate inference enrichment (issue #9).

Pure-Python, no OWM / Claude / Supabase calls. Forecast and climate helpers
are monkeypatched so coverage behavior can be checked deterministically.
"""

from datetime import date, datetime, timezone

import pytest

from services import trip_planner, weather

FORECAST_DAYS = [date(2026, 6, 1), date(2026, 6, 2), date(2026, 6, 3)]


def _entry(day: date, temp: float, condition: str = "Clouds", pop: float = 0.0):
    dt = datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc)
    return {
        "dt": int(dt.timestamp()),
        "main": {"temp": temp},
        "weather": [{"main": condition}],
        "pop": pop,
    }


@pytest.fixture(autouse=True)
def _fixed_forecast(monkeypatch):
    monkeypatch.setattr(
        weather,
        "_fetch_forecast",
        lambda lat, lon: {
            "city": {"timezone": 0},
            "list": [
                _entry(d, 20 + i, "Clouds", 0.1) for i, d in enumerate(FORECAST_DAYS)
            ],
        },
    )


def _weather_for(start: date, end: date):
    return weather.get_weather_for_destination(
        "Paris, France", start, end, lat=48.85, lon=2.35
    )


def test_full_coverage_returns_forecast_summary():
    full = _weather_for(date(2026, 6, 1), date(2026, 6, 3))
    assert full.coverage == "full_forecast"
    assert len(full.daily) == 3
    assert full.forecast_summary == full.summary
    assert full.inferred_summary is None


def test_partial_coverage_keeps_available_days():
    partial = _weather_for(date(2026, 6, 2), date(2026, 6, 5))
    assert partial.coverage == "partial_forecast"
    assert [d.date for d in partial.daily] == [date(2026, 6, 2), date(2026, 6, 3)]
    assert partial.forecast_summary
    assert "Forecast covers 2026-06-02 to 2026-06-03" in partial.summary


def test_missing_coverage_flags_inference_needed():
    missing = _weather_for(date(2026, 6, 10), date(2026, 6, 12))
    assert missing.coverage == "inferred_climate"
    assert missing.daily == []
    assert missing.forecast_summary is None


def test_inference_node_noops_for_full_forecast():
    full = _weather_for(date(2026, 6, 1), date(2026, 6, 3))
    assert trip_planner.infer_weather_if_needed_node({"weather": full}) == {}


def test_inference_node_enriches_partial_forecast(monkeypatch):
    monkeypatch.setattr(
        trip_planner,
        "infer_climate_summary",
        lambda state: "Remaining dates are likely warm and humid; this is a climate estimate.",
    )
    partial = _weather_for(date(2026, 6, 2), date(2026, 6, 5))
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


def test_inference_node_enriches_missing_forecast(monkeypatch):
    monkeypatch.setattr(
        trip_planner,
        "infer_climate_summary",
        lambda state: "Remaining dates are likely warm and humid; this is a climate estimate.",
    )
    missing = _weather_for(date(2026, 6, 10), date(2026, 6, 12))
    enriched = trip_planner.infer_weather_if_needed_node(
        {
            "destination": "Paris, France",
            "start_date": date(2026, 6, 10),
            "end_date": date(2026, 6, 12),
            "additional_notes": "",
            "weather": missing,
        }
    )["weather"]
    assert enriched.coverage == "inferred_climate"
    assert enriched.forecast_summary is None
    assert enriched.summary == enriched.inferred_summary


def test_climate_parser_tolerates_missing_key(monkeypatch):
    class FakeMessages:
        def create(self, **kwargs):
            return object()

    class FakeClient:
        messages = FakeMessages()

    monkeypatch.setattr(trip_planner, "client", lambda: FakeClient())
    monkeypatch.setattr(trip_planner, "parse_json", lambda resp: {})
    missing = _weather_for(date(2026, 6, 10), date(2026, 6, 12))
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
