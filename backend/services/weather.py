"""OpenWeatherMap forecast → today's high/low/conditions/precip (metric)."""

import logging
import os
import time
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from typing import TypedDict
from schemas import TripWeather, TripWeatherDay

import httpx

# #88: the OWM key rides in the request URL's query string, and httpx logs full
# URLs at INFO — silence its request logger so the key never hits the logs.
logging.getLogger("httpx").setLevel(logging.WARNING)

OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"
OWM_GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"
CACHE_TTL = 30 * 60  # 30 minutes

_FORECAST_CACHE: dict[tuple[float, float], tuple[float, dict]] = {}
_FORECAST_TTL = 30 * 60  # 30 minutes


class TodayWeather(TypedDict):
    temp_high_c: float
    temp_low_c: float
    conditions: str
    precip_chance: float  # 0..1
    wind_kmh: float

class DestinationNotFound(ValueError):
    """OpenWeatherMap couldn't geocode this destination string."""

_cache: dict[tuple[float, float], tuple[float, TodayWeather]] = {}


def get_today(lat: float | None = None, lon: float | None = None) -> TodayWeather:
    if lat is None or lon is None:
        lat = float(os.environ["WEATHER_LAT"])
        lon = float(os.environ["WEATHER_LON"])
    key = (round(lat, 2), round(lon, 2))
    now = time.time()
    cached = _cache.get(key)
    if cached and now - cached[0] < CACHE_TTL:
        return cached[1]

    api_key = os.environ["OPENWEATHERMAP_API_KEY"]
    resp = httpx.get(
        OWM_URL,
        params={"lat": lat, "lon": lon, "units": "metric", "appid": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    today_utc_date = datetime.now(timezone.utc).date()
    todays = [e for e in data["list"] if _entry_local_date(e, data) == today_utc_date]
    if not todays:
        # OWM forecast starts at next 3-hour slot; if today is empty, use the first slot.
        todays = data["list"][:1]

    temps = [e["main"]["temp"] for e in todays]
    descriptions = [e["weather"][0]["main"] for e in todays]
    pops = [e.get("pop", 0.0) for e in todays]
    winds = [e.get("wind", {}).get("speed", 0.0) for e in todays]  # m/s

    weather: TodayWeather = {
        "temp_high_c": round(max(temps), 1),
        "temp_low_c": round(min(temps), 1),
        "conditions": Counter(descriptions).most_common(1)[0][0],
        "precip_chance": round(max(pops), 2),
        "wind_kmh": round(max(winds) * 3.6, 1),
    }
    _cache[key] = (now, weather)
    return weather


def _entry_local_date(entry: dict, data: dict):
    tz_offset_seconds = data.get("city", {}).get("timezone", 0)
    dt = datetime.fromtimestamp(entry["dt"] + tz_offset_seconds, tz=timezone.utc)
    return dt.date()


def _destination_to_coords(destination: str) -> tuple[float, float]:
    """Convert a user-friendly location (e.g. "Paris, France") to lat/lon."""

    api_key = os.environ["OPENWEATHERMAP_API_KEY"]
    resp = httpx.get(
        OWM_GEO_URL,
        params={"q": destination, "limit": 1, "appid": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()

    if not data:
        raise DestinationNotFound(f"No location found for {destination!r}")

    lat = data[0]["lat"]
    lon = data[0]["lon"]
    return lat, lon


def _rollup_day(entries: list[dict], date: date) -> TripWeatherDay:
    temps = [e["main"]["temp"] for e in entries]

    return TripWeatherDay(
        date=date,
        high_c=round(max(temps), 1),
        low_c=round(min(temps), 1),
        conditions=Counter(e["weather"][0]["main"] for e in entries).most_common(1)[0][
            0
        ],
        precip_chance=round(max(e.get("pop", 0.0) for e in entries), 2),
    )


def _fetch_forecast(lat: float, lon: float) -> dict:
    key = (round(lat, 2), round(lon, 2))
    now = time.time()
    cached = _FORECAST_CACHE.get(key)
    if cached and now - cached[0] < _FORECAST_TTL:
        return cached[1]


    api_key = os.environ["OPENWEATHERMAP_API_KEY"]
    resp = httpx.get(
        OWM_URL,
        params={"lat": lat, "lon": lon, "units": "metric", "appid": api_key},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    _FORECAST_CACHE[key] = (now, data)
    return data


def _date_range(start_date: date, end_date: date) -> list[date]:
    return [
        start_date + timedelta(days=i)
        for i in range((end_date - start_date).days + 1)
    ]


def _summarize_conditions(daily: list[TripWeatherDay]) -> str:
    max_temp = max(d.high_c for d in daily)
    min_temp = min(d.low_c for d in daily)
    most_common_conditions = Counter(d.conditions for d in daily).most_common(1)[
        0
    ][0]
    max_precip = max(d.precip_chance for d in daily)

    if max_precip > 0.5:    percip_summary = f"High chance of precipitation: {max_precip*100:.0f}%"
    elif max_precip > 0.2:  percip_summary = f"Moderate chance: {max_precip*100:.0f}%"
    elif max_precip > 0.05: percip_summary = f"Low chance: {max_precip*100:.0f}%"
    else:                   percip_summary = "No precipitation expected."


    return (
        f"Trip weather: high {max_temp}°C, low {min_temp}°C, "
        f"mostly {most_common_conditions}. {percip_summary}"
    )


def _format_date_span(days: list[date]) -> str:
    if len(days) == 1:
        return days[0].isoformat()
    return f"{days[0].isoformat()} to {days[-1].isoformat()}"


def get_weather_for_destination(
    destination: str,
    start_date: date,
    end_date: date,
    lat: float | None = None,
    lon: float | None = None,
) -> TripWeather:
    if lat is None or lon is None:
        lat, lon = _destination_to_coords(destination)
    raw = _fetch_forecast(lat, lon)

    by_date: dict[date, list[dict]] = {}

    for entry in raw["list"]:
        local_date = _entry_local_date(entry, raw)

        by_date.setdefault(local_date, []).append(entry)

    requested_dates = _date_range(start_date, end_date)
    covered_dates = [d for d in requested_dates if d in by_date]
    daily = [
        _rollup_day(by_date[d], d)
        for d in covered_dates
    ]

    if not daily:
        return TripWeather(
            daily=[],
            summary=(
                "Forecast data is outside OpenWeatherMap's 5-day window; "
                "a climate estimate is needed for this trip."
            ),
            coverage="inferred_climate",
        )

    forecast_summary = _summarize_conditions(daily)
    if len(covered_dates) == len(requested_dates):
        coverage = "full_forecast"
        summary = forecast_summary
    else:
        coverage = "partial_forecast"
        summary = (
            f"Forecast covers {_format_date_span(covered_dates)}. "
            f"{forecast_summary}"
        )

    return TripWeather(
        daily=daily,
        summary=summary,
        coverage=coverage,
        forecast_summary=summary,
    )
