from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth import require_password
from db.supabase import client as supabase
from schemas import Preference, PreferenceCreate, PreferenceUpdate, Profile, ProfileUpdate

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
    payload = body.model_dump()
    payload["updated_at"] = _now()

    if existing.data:
        row_id = existing.data[0]["id"]
        res = (
            supabase()
            .table("profile")
            .update(payload)
            .eq("id", row_id)
            .execute()
        )
    else:
        res = supabase().table("profile").insert(payload).execute()

    if not res.data:
        raise HTTPException(status_code=500, detail="Profile write failed")
    return res.data[0]


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

    res = (
        supabase()
        .table("preferences")
        .update(patch)
        .eq("id", pref_id)
        .execute()
    )
    if not res.data:
        raise HTTPException(status_code=500, detail="Preference update failed")
    return res.data[0]


@router.delete("/preferences/{pref_id}", status_code=204)
def delete_preference(pref_id: str):
    existing = supabase().table("preferences").select("source").eq("id", pref_id).execute()
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
