"""Regression tests for credentials embedded in upstream request URLs (#150)."""

import logging
import traceback
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from fastapi import HTTPException

from routers import geo
from services import calendar, weather
from services.http_errors import UpstreamHTTPError


def _error_response(status: int, url: str) -> httpx.Response:
    return httpx.Response(status, request=httpx.Request("GET", url))


def test_geo_error_log_excludes_owm_key(monkeypatch, caplog):
    api_key = "super-secret-owm-key"
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", api_key)
    monkeypatch.setattr(
        geo.httpx,
        "get",
        lambda *args, **kwargs: _error_response(
            401, f"https://api.openweathermap.org/geo/1.0/direct?appid={api_key}"
        ),
    )
    caplog.set_level(logging.WARNING, logger="wardrobe.geo")

    with pytest.raises(HTTPException) as captured:
        geo.search(q="Paris", limit=5)

    assert captured.value.status_code == 502
    assert "HTTPStatusError (status=401)" in caplog.text
    assert api_key not in caplog.text


@pytest.mark.parametrize(
    "call",
    [
        lambda: weather.get_today(lat=40.7, lon=-74.0),
        lambda: weather._destination_to_coords("Paris, France"),
        lambda: weather._fetch_forecast(48.85, 2.35),
    ],
)
def test_weather_errors_exclude_owm_key_from_outer_tracebacks(monkeypatch, call):
    api_key = "super-secret-owm-key"
    monkeypatch.setenv("OPENWEATHERMAP_API_KEY", api_key)
    weather._cache.clear()
    weather._FORECAST_CACHE.clear()
    monkeypatch.setattr(
        weather.httpx,
        "get",
        lambda *args, **kwargs: _error_response(
            401, f"https://api.openweathermap.org/data/2.5/forecast?appid={api_key}"
        ),
    )

    with pytest.raises(UpstreamHTTPError) as captured:
        call()

    rendered = "".join(
        traceback.format_exception(
            type(captured.value), captured.value, captured.value.__traceback__
        )
    )
    assert "OpenWeatherMap request failed: HTTPStatusError (status=401)" in rendered
    assert api_key not in rendered


def test_calendar_failure_log_excludes_secret_ics_url(monkeypatch, caplog):
    secret_url = "https://calendar.example/private-feed/secret-token/basic.ics"
    monkeypatch.setenv("CALENDAR_ICS_URL", secret_url)
    monkeypatch.setattr(
        calendar.httpx,
        "get",
        lambda *args, **kwargs: _error_response(403, secret_url),
    )
    caplog.set_level(logging.WARNING, logger="wardrobe.calendar")

    modes = [{"name": "Smart casual", "description": "default"}]
    result = calendar.calendar_modes(
        modes,
        floor="Smart casual",
        tz=ZoneInfo("America/New_York"),
        now=datetime(2026, 9, 22, 6, 0, tzinfo=ZoneInfo("America/New_York")),
    )

    assert result == (modes, "", "")
    assert "Calendar request failed: HTTPStatusError (status=403)" in caplog.text
    assert secret_url not in caplog.text
    assert "secret-token" not in caplog.text
