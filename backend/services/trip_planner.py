"""Trip planner — agentic packing recommendations.

This module is the integration point for the LangGraph pipeline. It exposes a
single `run(req)` function that the router calls; everything else is internal.

V1 behavior:
- This file ships with `_mock_response()` so the frontend can be built and
  tested without LangGraph in place.
- Replace the body of `run()` with the real LangGraph invocation. The graph
  should return a TripPlanResponse-shaped object.

Useful existing utilities to reuse inside your graph:
- backend.services.weather: today's weather for given coords (needs extension
  for multi-day forecast + destination geocoding).
- backend.services.claude:   Anthropic client + JSON-parse helpers.
- backend.db.supabase:       Supabase client (use service_role; bypass RLS).
"""

from datetime import date, timedelta

from db.supabase import client as supabase
from schemas import (
    ClothingItem,
    PackingCategory,
    TripPlanRequest,
    TripPlanResponse,
    TripWeather,
    TripWeatherDay,
)

# ---- Public entrypoint ----------------------------------------------------


def run(req: TripPlanRequest) -> TripPlanResponse:
    """Generate a packing plan for the trip.

    TODO(you): replace this body with the LangGraph invocation. The graph's
    final node should produce data shaped like `TripPlanResponse`.
    """
    return _mock_response(req)


# ---- Mock (delete once LangGraph is wired) --------------------------------


def _mock_response(req: TripPlanRequest) -> TripPlanResponse:
    """Best-effort mock so the frontend has something realistic to render.

    Pulls real items from the catalog when available, buckets them into
    categories, and fabricates a plausible weather/gaps/purchases payload.
    """
    duration_days = (req.end_date - req.start_date).days + 1

    rows = (
        supabase()
        .table("clothing_items")
        .select("*")
        .eq("available", True)
        .limit(40)
        .execute()
        .data
        or []
    )
    items_by_category: dict[str, list[ClothingItem]] = {}
    for row in rows:
        cat = _categorize(row.get("type", ""))
        items_by_category.setdefault(cat, []).append(ClothingItem(**row))

    packing_list: list[PackingCategory] = []
    for cat in ("dresses", "tops", "bottoms", "outerwear", "shoes", "accessories", "other"):
        bucket = items_by_category.get(cat, [])
        if bucket:
            packing_list.append(PackingCategory(category=cat, items=bucket[:4]))

    weather = TripWeather(
        summary="Sunny, 26–30°C during the day, cool 14–17°C in the evening. No precipitation expected.",
        daily=[
            TripWeatherDay(
                date=req.start_date + timedelta(days=i),
                high_c=29.0,
                low_c=14.0,
                conditions="Sunny",
                precip_chance=0.0,
            )
            for i in range(duration_days)
        ],
    )

    return TripPlanResponse(
        destination=req.destination,
        start_date=req.start_date,
        end_date=req.end_date,
        duration_days=duration_days,
        weather=weather,
        packing_list=packing_list,
        gaps=[
            "Linen wide-leg pants for hot daytime walks",
            "Lightweight sun hat",
        ],
        purchase_suggestions=[
            {
                "gap": "Linen wide-leg pants for hot daytime walks",
                "results": [
                    {
                        "title": "Wide-Leg Linen Pants",
                        "url": "https://www.madewell.com/example-linen-pants",
                        "image_url": "https://placehold.co/300x300?text=Linen+Pants",
                        "price": "$89",
                        "retailer": "Madewell",
                    },
                    {
                        "title": "Pleated Linen Trousers",
                        "url": "https://www.everlane.com/example-trousers",
                        "image_url": "https://placehold.co/300x300?text=Trousers",
                        "price": "$118",
                        "retailer": "Everlane",
                    },
                ],
            },
            {
                "gap": "Lightweight sun hat",
                "results": [
                    {
                        "title": "Packable Straw Sun Hat",
                        "url": "https://www.example.com/sun-hat",
                        "image_url": "https://placehold.co/300x300?text=Sun+Hat",
                        "price": "$45",
                        "retailer": "Quince",
                    }
                ],
            },
        ],
        reasoning=(
            f"For {duration_days} days in {req.destination} with warm sunny weather, "
            "we focused on breathable layers with elevated touches for evening dining. "
            "Cobblestone-friendly shoes and a light layer for cool mornings. Two gaps "
            "flagged for purchase to round out the lineup."
        ),
    )


def _categorize(item_type: str) -> str:
    t = (item_type or "").lower()
    if t == "dress":
        return "dresses"
    if t in {"shirt", "t-shirt", "blouse", "sweater"}:
        return "tops"
    if t in {"trousers", "jeans", "shorts", "skirt"}:
        return "bottoms"
    if t in {"jacket", "coat", "vest"}:
        return "outerwear"
    if t in {"shoes", "boots", "sneakers", "sandals"}:
        return "shoes"
    if t in {"bag", "scarf", "hat", "belt", "accessory"}:
        return "accessories"
    return "other"
