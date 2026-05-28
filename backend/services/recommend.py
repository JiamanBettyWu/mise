"""Shared outfit recommendation logic — used by the API router and the daily cron."""

from db.supabase import client as supabase
from services.claude import recommend_outfits
from services.weather import TodayWeather, get_today

WARDROBE_FIELDS = (
    "id, name, type, color, formality, season, fabric, brand, description"
)


def recommend(
    travel_mode: bool = False,
    notes: str = "",
    n: int = 3,
    lat: float | None = None,
    lon: float | None = None,
    modes: list[dict] | None = None,
) -> dict:
    weather = get_today(lat=lat, lon=lon)

    q = supabase().table("clothing_items").select(WARDROBE_FIELDS).eq("available", True)
    if travel_mode:
        q = q.eq("in_travel_bag", True)
    res = q.execute()
    wardrobe = res.data or []

    outfits = recommend_outfits(
        weather=weather, wardrobe=wardrobe, n=n, notes=notes, modes=modes
    )

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
            "label": o.get("label", ""),
            "items": (
                []
                if _is_skip(o.get("reasoning", ""))
                else [by_id[iid] for iid in o.get("item_ids", []) if iid in by_id]
            ),
            "reasoning": o.get("reasoning", ""),
        }
        for o in outfits
    ]

    return {"weather": weather, "outfits": hydrated, "wardrobe_size": len(wardrobe)}


def _is_skip(reasoning: str) -> bool:
    """True when Claude signaled 'no recommendation' for this mode.

    The outfit prompt instructs Claude to skip a mode by returning empty
    item_ids and a reasoning that begins with 'No <mode> recommendation
    available today'. Some responses follow the *text* convention but still
    return item_ids — we defensively drop the items so the email template's
    empty-state branch fires. Anchor on the prompt's exact phrasing.
    """
    r = reasoning.strip().lower()
    return r.startswith("no ") and "recommendation available" in r
