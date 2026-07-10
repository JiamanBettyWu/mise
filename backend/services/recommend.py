"""Shared outfit recommendation logic — used by the API router and the daily cron."""

import logging
from datetime import date

from db.supabase import client as supabase
from observability import op
from services.claude import recommend_outfits
from services.outfit_history import (
    blocked_combos,
    log_outfits,
    recent_combos,
    recent_feedback_outfits,
    recent_picks,
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


def _get_active_preferences() -> tuple[list[str], list[str]]:
    """Return (user_texts, inferred_texts) for all active preferences.

    Split by source because they enter the prompt differently: user-authored
    prefs (#61) are HARD constraints, inferred ones (#62) are SOFT — a weekly
    job's guess that may be wrong, so it nudges rather than binds. See
    claude._preferences_block vs _inferred_preferences_block.
    """
    try:
        res = (
            supabase()
            .table("preferences")
            .select("text, source")
            .eq("status", "active")
            .order("created_at")
            .execute()
        )
        user, inferred = [], []
        for row in res.data or []:
            (inferred if row.get("source") == "inferred" else user).append(row["text"])
        return user, inferred
    except Exception:
        log.warning("could not read preferences", exc_info=True)
        return [], []


WARDROBE_FIELDS = (
    "id, name, type, color, formality, season, fabric, warmth, brand, description"
)


@op  # Weave trace root (#85); the whole decision tree hangs off this node.
def recommend(
    travel_mode: bool = False,
    notes: str = "",
    n: int = 3,
    lat: float | None = None,
    lon: float | None = None,
    modes: list[dict] | None = None,
    persist: bool = True,
    weather: dict | None = None,
    wardrobe: list[dict] | None = None,
    history_rows: list[dict] | None = None,
    today: date | None = None,
) -> dict:
    # persist=False runs the full decision path (weather → gate → sample →
    # Claude pick) but skips the outfit_history write — the read-only mode for
    # Weave trace runs (#85) and Phase 2 eval replays, so probing the pipeline
    # never pollutes the 👍/👎 dataset it learns from. history_id comes back
    # None; the output shape is otherwise identical to a persisted run.
    #
    # weather / wardrobe / history_rows / today are the offline-eval seam
    # (#118), mirroring how eval_trip.py replaces the trip graph's fetch nodes:
    # each one, when given, replaces the corresponding live fetch so the eval
    # runs the real gate → sampler → Claude path over a frozen scenario.
    # Preferences (#61/#62) still read live, same as the eval_trip Haiku
    # planner. Production callers pass none of them.
    #
    # Profile home location is the weather fallback; env vars are the last resort.
    today = today or date.today()
    if weather is None:
        if lat is None or lon is None:
            home = _get_home_coords()
            if home:
                lat, lon = home
        weather = get_today(lat=lat, lon=lon)
    user_prefs, inferred_prefs = _get_active_preferences()

    frozen_catalog = wardrobe is not None
    if wardrobe is None:
        q = (
            supabase()
            .table("clothing_items")
            .select(WARDROBE_FIELDS)
            .eq("available", True)
        )
        if travel_mode:
            q = q.eq("in_travel_bag", True)
        wardrobe = q.execute().data or []
    wardrobe_size = len(wardrobe)

    # Extremes gate first (issue #18) so absurd items can't displace useful
    # ones in the sample, then the recency-weighted subset (issue #15): items
    # recently recommended in any of today's modes are less likely but never
    # excluded. Small-category counts inside sampling see the post-gate pool —
    # substitutes that don't exist *today* shouldn't count.
    wearable = gate_extremes(wardrobe, weather)
    candidate_pool = sample_wardrobe(
        wearable, modes=modes, today=today, history_rows=history_rows
    )

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
    frozen_names = (
        {item["id"]: item.get("name", "") for item in wardrobe}
        if history_rows is not None
        else None
    )
    outfits = recommend_outfits(
        weather=weather,
        wardrobe=candidate_pool,
        n=n,
        notes=notes,
        modes=modes,
        feedback_entries=recent_feedback_outfits(
            today=today, rows=history_rows, names_by_id=frozen_names
        ),
        blocked_combos=blocked_combos(rows=history_rows),
        recent_combos=recent_combos(today=today, rows=history_rows),
        preferences=user_prefs or None,
        inferred_preferences=inferred_prefs or None,
        # Choice-level variety signal (#135): show the model this week's
        # already-picked items so it can prefer fresh pieces — the sampler
        # only shapes the pool, not which pool item the model reaches for.
        recent_picks=recent_picks(
            today=today, rows=history_rows, names_by_id=frozen_names
        ),
    )

    history_ids = (
        log_outfits(
            today,
            [(o.get("label", ""), o.get("item_ids", [])) for o in outfits],
            weather=weather,
            notes=notes,
        )
        if persist
        else [None] * len(outfits)
    )

    # Hydrate with full item objects so the frontend can show photos without
    # re-querying. Frozen-wardrobe runs (#118) hydrate from the injected
    # catalog instead — the frozen rows carry only WARDROBE_FIELDS, but the
    # eval scorers never need photo_url.
    if frozen_catalog:
        by_id = {item["id"]: item for item in wardrobe}
    else:
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
