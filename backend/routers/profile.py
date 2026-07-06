from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException

from auth import require_password
from db.supabase import client as supabase
from schemas import (
    Preference,
    PreferenceCreate,
    PreferenceUpdate,
    Profile,
    ProfileUpdate,
)
from services.stats import aggregate_outfits, aggregate_usage, range_cutoff

router = APIRouter(prefix="/profile", dependencies=[Depends(require_password)])


# ---------------------------------------------------------------------------
# #62 contracts, as pure functions (tested in tests/test_preferences.py)
# ---------------------------------------------------------------------------


def apply_promotion(source: str, patch: dict) -> dict:
    """Editing an inferred pref's text promotes it to user-owned (#61 → #62 contract).

    Once promoted, the weekly inference job (#62) reads it as context but never
    writes to it again. Status-only patches don't promote — un-rejecting an
    inferred pref shouldn't claim ownership of it.
    """
    if source == "inferred" and "text" in patch:
        return {**patch, "source": "user"}
    return patch


def delete_disposition(source: str) -> str:
    """'delete' for user prefs, 'tombstone' for inferred ones.

    #62 re-derives the inferred set every run, so a hard delete would be
    resurrected next week; status='rejected' is kept as the do-not-re-emit
    marker. User prefs have no job that could bring them back.
    """
    return "tombstone" if source == "inferred" else "delete"


# ---------------------------------------------------------------------------
# Profile (single-row home location)
# ---------------------------------------------------------------------------


@router.get("", response_model=Profile)
def get_profile():
    res = supabase().table("profile").select("*").limit(1).execute()
    if res.data:
        return res.data[0]
    return Profile()


@router.put("", response_model=Profile)
def upsert_profile(body: ProfileUpdate):
    existing = supabase().table("profile").select("id").limit(1).execute()
    payload = body.model_dump(exclude_unset=True)
    if payload.get("shopping_department") is None:
        payload.pop("shopping_department", None)
    payload["updated_at"] = _now()

    if existing.data:
        row_id = existing.data[0]["id"]
        res = supabase().table("profile").update(payload).eq("id", row_id).execute()
    else:
        res = supabase().table("profile").insert(payload).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Profile write failed")
    return res.data[0]


# ---------------------------------------------------------------------------
# Stats (#115) — all aggregation server-side; math lives in services/stats.py
# ---------------------------------------------------------------------------


@router.get("/stats")
def get_stats(range: Literal["7d", "30d", "90d", "all"] = "30d"):
    cutoff = range_cutoff(range)

    usage_q = (
        supabase()
        .table("llm_usage")
        .select(
            "call_type, model, input_tokens, output_tokens, "
            "cache_creation_input_tokens, cache_read_input_tokens"
        )
    )
    outfits_q = supabase().table("outfit_history").select("item_ids, feedback")
    if cutoff:
        usage_q = usage_q.gte("created_at", cutoff)
        outfits_q = outfits_q.gte("created_at", cutoff)

    usage = aggregate_usage(usage_q.execute().data or [])
    outfits = aggregate_outfits(outfits_q.execute().data or [])

    # Trips planned = trip_plan calls in llm_usage: exactly one per plan
    # since #114. #128 added a trip_plans table, but that's for *saved* plans
    # only (explicit, optional action) — this stat counts every generation,
    # all-time and unaffected by later deletes, so it stays on llm_usage.
    # Shares the since-#114 caveat.
    trips = usage["by_call_type"].get("trip_plan", {}).get("calls", 0)

    # Token data only exists from #114's deploy onward — surface the earliest
    # row so "All time" can be labeled "since <month>" instead of lying.
    first = (
        supabase()
        .table("llm_usage")
        .select("created_at")
        .order("created_at")
        .limit(1)
        .execute()
    )
    usage_since = first.data[0]["created_at"] if first.data else None

    top_ids = [item_id for item_id, _ in outfits["top_item_counts"]]
    top_items = []
    if top_ids:
        items_res = (
            supabase()
            .table("clothing_items")
            .select("id, name, photo_url")
            .in_("id", top_ids)
            .execute()
        )
        by_id = {i["id"]: i for i in items_res.data or []}
        # keep frequency order; drop ids whose item was deleted
        top_items = [
            {**by_id[item_id], "count": count}
            for item_id, count in outfits["top_item_counts"]
            if item_id in by_id
        ]

    return {
        "range": range,
        "usage_since": usage_since,
        "usage": {
            "total_calls": usage["total_calls"],
            "total_tokens": usage["total_tokens"],
            "estimated_cost": usage["total_cost"],
            "has_unpriced": usage["has_unpriced"],
            "by_call_type": usage["by_call_type"],
        },
        "outfits": outfits["outfits"],
        "feedback_count": outfits["feedback_count"],
        "thumbs_up_rate": outfits["thumbs_up_rate"],
        "trips": trips,
        "top_items": top_items,
    }


# ---------------------------------------------------------------------------
# Preferences
# ---------------------------------------------------------------------------


@router.get("/preferences", response_model=list[Preference])
def list_preferences():
    res = (
        supabase()
        .table("preferences")
        .select("*")
        .eq("status", "active")
        .order("created_at")
        .execute()
    )
    return res.data or []


@router.post("/preferences", response_model=Preference, status_code=201)
def create_preference(body: PreferenceCreate):
    res = (
        supabase()
        .table("preferences")
        .insert({"text": body.text, "source": "user"})
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="Preference write failed")
    return res.data[0]


@router.patch("/preferences/{pref_id}", response_model=Preference)
def update_preference(pref_id: str, body: PreferenceUpdate):
    existing = supabase().table("preferences").select("*").eq("id", pref_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Preference not found")

    patch = body.model_dump(exclude_none=True)
    patch = apply_promotion(existing.data[0]["source"], patch)
    patch["updated_at"] = _now()

    res = supabase().table("preferences").update(patch).eq("id", pref_id).execute()
    if not res.data:
        raise HTTPException(status_code=500, detail="Preference update failed")
    return res.data[0]


@router.delete("/preferences/{pref_id}", status_code=204)
def delete_preference(pref_id: str):
    existing = (
        supabase().table("preferences").select("source").eq("id", pref_id).execute()
    )
    if not existing.data:
        raise HTTPException(status_code=404, detail="Preference not found")

    if delete_disposition(existing.data[0]["source"]) == "tombstone":
        supabase().table("preferences").update(
            {"status": "rejected", "updated_at": _now()}
        ).eq("id", pref_id).execute()
    else:
        supabase().table("preferences").delete().eq("id", pref_id).execute()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
