from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException

from auth import require_password
from db.supabase import client as supabase
from schemas import Preference, PreferenceCreate, PreferenceUpdate, Profile, ProfileUpdate

router = APIRouter(prefix="/profile", dependencies=[Depends(require_password)])


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
    now = datetime.now(timezone.utc).isoformat()
    payload = {k: v for k, v in body.model_dump().items()}
    payload["updated_at"] = now

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

    row = existing.data[0]
    now = datetime.now(timezone.utc).isoformat()
    patch = {k: v for k, v in body.model_dump(exclude_none=True).items()}
    patch["updated_at"] = now

    # Editing an inferred pref promotes it to user-owned (#61 contract for #62).
    if row["source"] == "inferred" and "text" in patch:
        patch["source"] = "user"

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

    source = existing.data[0]["source"]
    if source == "inferred":
        # Tombstone so #62's weekly job won't resurrect it.
        now = datetime.now(timezone.utc).isoformat()
        supabase().table("preferences").update({"status": "rejected", "updated_at": now}).eq("id", pref_id).execute()
    else:
        supabase().table("preferences").delete().eq("id", pref_id).execute()
