"""Server-side proxy for OpenWeatherMap geocoding.

Keeps the OWM key out of the client bundle and lets the frontend autocomplete
destinations against the same provider the weather node uses.
"""

import logging
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query

from auth import require_password

log = logging.getLogger("wardrobe.geo")

OWM_GEO_URL = "https://api.openweathermap.org/geo/1.0/direct"

router = APIRouter(
    prefix="/geo",
    tags=["geo"],
    dependencies=[Depends(require_password)],
)


@router.get("/search")
def search(
    q: str = Query(..., min_length=2, max_length=100),
    limit: int = Query(5, ge=1, le=10),
) -> list[dict]:
    api_key = os.environ["OPENWEATHERMAP_API_KEY"]
    try:
        resp = httpx.get(
            OWM_GEO_URL,
            params={"q": q, "limit": limit, "appid": api_key},
            timeout=5,
        )
        resp.raise_for_status()
    except httpx.HTTPError as e:
        log.warning("OWM geocoding failed for %r: %s", q, e)
        raise HTTPException(status_code=502, detail="Geocoding upstream failed")

    return [
        {
            "name": row.get("name"),
            "country": row.get("country"),
            "state": row.get("state"),
            "lat": row.get("lat"),
            "lon": row.get("lon"),
        }
        for row in resp.json()
    ]
