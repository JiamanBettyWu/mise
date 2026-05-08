"""Shared outfit recommendation logic — used by the API router and the daily cron."""

from db.supabase import client as supabase
from services.claude import recommend_outfits
from services.weather import TodayWeather, get_today

WARDROBE_FIELDS = (
    "id, name, type, color, formality, season, fabric, brand, description"
)


def recommend(travel_mode: bool = False, notes: str = "", n: int = 3) -> dict:
    weather = get_today()

    q = supabase().table("clothing_items").select(WARDROBE_FIELDS).eq("available", True)
    if travel_mode:
        q = q.eq("in_travel_bag", True)
    res = q.execute()
    wardrobe = res.data or []

    outfits = recommend_outfits(weather=weather, wardrobe=wardrobe, n=n, notes=notes)

    # Hydrate with full item objects so the frontend can show photos without re-querying.
    full = (
        supabase()
        .table("clothing_items")
        .select("*")
        .in_("id", [iid for o in outfits for iid in o.get("item_ids", [])])
        .execute()
    )
    by_id = {row["id"]: row for row in (full.data or [])}

    hydrated = [
        {
            "items": [by_id[iid] for iid in o.get("item_ids", []) if iid in by_id],
            "reasoning": o.get("reasoning", ""),
        }
        for o in outfits
    ]

    return {"weather": weather, "outfits": hydrated, "wardrobe_size": len(wardrobe)}
