"""OpenWeatherMap forecast → today's high/low/conditions/precip (metric)."""

import os
import time
from collections import Counter
from datetime import datetime, timezone
from typing import TypedDict

import httpx

OWM_URL = "https://api.openweathermap.org/data/2.5/forecast"
CACHE_TTL = 30 * 60  # 30 minutes


class TodayWeather(TypedDict):
    temp_high_c: float
    temp_low_c: float
    conditions: str
    precip_chance: float  # 0..1
    wind_kmh: float


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
