"""Shared outfit recommendation logic — used by the API router and the daily cron."""

import logging
from datetime import date

from db.supabase import client as supabase
from services.claude import recommend_outfits
from services.outfit_history import (
    blocked_combos,
    log_outfits,
    recent_combos,
    recent_feedback_outfits,
    sample_wardrobe,
)
from services.weather import get_today
from services.weather_gate import gate_extremes

log = logging.getLogger("wardrobe.recommend")


def _get_home_coords() -> tuple[float, float] | None:
    """Return (lat, lon) from the profile row, or None if not set."""
    try:
        res = supabase().table("profile").select("home_lat,home_lon").limit(1).execute()
        if res.data:
            row = res.data[0]
            if row.get("home_lat") is not None and row.get("home_lon") is not None:
                return float(row["home_lat"]), float(row["home_lon"])
    except Exception:
        log.warning("could not read profile for home coords", exc_info=True)
    return None


def _get_active_preferences() -> list[str]:
    """Return the text of all active user-provided preferences."""
    try:
        res = (
            supabase()
            .table("preferences")
            .select("text")
            .eq("status", "active")
            .order("created_at")
            .execute()
        )
        return [row["text"] for row in (res.data or [])]
    except Exception:
        log.warning("could not read preferences", exc_info=True)
        return []

WARDROBE_FIELDS = (
    "id, name, type, color, formality, season, fabric, warmth, brand, description"
)


def recommend(
    travel_mode: bool = False,
    notes: str = "",
    n: int = 3,
    lat: float | None = None,
    lon: float | None = None,
    modes: list[dict] | None = None,
) -> dict:
    # Profile home location is the weather fallback; env vars are the last resort.
    if lat is None or lon is None:
        home = _get_home_coords()
        if home:
            lat, lon = home

    weather = get_today(lat=lat, lon=lon)
    preferences = _get_active_preferences()

    q = supabase().table("clothing_items").select(WARDROBE_FIELDS).eq("available", True)
    if travel_mode:
        q = q.eq("in_travel_bag", True)
    res = q.execute()
    wardrobe = res.data or []
    wardrobe_size = len(wardrobe)

    # Extremes gate first (issue #18) so absurd items can't displace useful
    # ones in the sample, then the recency-weighted subset (issue #15): items
    # recently recommended in any of today's modes are less likely but never
    # excluded. Small-category counts inside sampling see the post-gate pool —
    # substitutes that don't exist *today* shouldn't count.
    wearable = gate_extremes(wardrobe, weather)
    candidate_pool = sample_wardrobe(wearable, modes=modes)

    # One line of observability (#63): when a mode lacks the right item, this
    # answers "was it sampled out of the pool, or did the model ignore it?"
    log.info(
        "candidate pool (%d of %d after gate + sampling): %s",
        len(candidate_pool),
        wardrobe_size,
        ", ".join(sorted(item.get("name", item["id"]) for item in candidate_pool)),
    )

    # Recent thumbed outfits ride along as prompt context (#59) — the
    # combination-level memory the per-item multipliers can't carry — while
    # combination-attributed 👎s (#60) and exact sets from the last 7 days
    # (#17) are hard candidate blocklists (#63): set-level dedup in code;
    # item-level rotation stays the sampler's job.
    outfits = recommend_outfits(
        weather=weather,
        wardrobe=candidate_pool,
        n=n,
        notes=notes,
        modes=modes,
        feedback_entries=recent_feedback_outfits(),
        blocked_combos=blocked_combos(),
        recent_combos=recent_combos(),
        preferences=preferences or None,
    )

    history_ids = log_outfits(
        date.today(),
        [(o.get("label", ""), o.get("item_ids", [])) for o in outfits],
        weather=weather,
        notes=notes,
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
            # Outfit_history row id for feedback links (#39); None for skips.
            "history_id": hid,
        }
        for o, hid in zip(outfits, history_ids)
    ]

    return {"weather": weather, "outfits": hydrated, "wardrobe_size": wardrobe_size}


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
