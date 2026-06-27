"""Tests for the #61 preference plumbing.

Pure-Python, no Supabase / Claude calls: _preferences_block renders the prompt
section, and the two routers/profile helpers encode the #62 contracts —
promote-on-edit and tombstone-on-delete. Those contracts are load-bearing:
#62's weekly job re-derives the inferred set every run, so the router is the
only thing standing between "dismissed" and "resurrected next Monday".
"""

from routers.profile import apply_promotion, delete_disposition
from schemas import Profile, ProfileUpdate
from services.claude import _inferred_preferences_block, _preferences_block

# --- _preferences_block (user-authored → hard constraints) ---


def test_block_renders_one_bullet_per_preference():
    block = _preferences_block(
        ["No sporty footwear with elevated outfits", "Prefer monochrome"]
    )
    assert block == (
        "User preferences:\n"
        "- No sporty footwear with elevated outfits\n"
        "- Prefer monochrome"
    )


def test_block_empty_list_renders_nothing():
    assert _preferences_block([]) == ""


# --- _inferred_preferences_block (#62 inferred → soft, separate header) ---


def test_inferred_block_uses_a_distinct_header():
    block = _inferred_preferences_block(["Likes earth tones on cold days"])
    assert block == "Learned preferences:\n- Likes earth tones on cold days"
    # Must NOT reuse the hard-constraint header, or the soft/hard distinction
    # the system prompt draws collapses.
    assert "User preferences" not in block


def test_inferred_block_empty_list_renders_nothing():
    assert _inferred_preferences_block([]) == ""


# --- profile shopping_department (#81 backend-only setting) ---


def test_profile_defaults_to_womens_shopping_department():
    assert Profile().shopping_department == "womens"


def test_profile_update_can_carry_shopping_department_without_ui():
    patch = ProfileUpdate(shopping_department="unisex")
    assert patch.model_dump(exclude_unset=True) == {"shopping_department": "unisex"}


# --- apply_promotion (#62 contract: editing an inferred pref makes it yours) ---


def test_text_edit_promotes_inferred_to_user():
    patch = apply_promotion(
        "inferred", {"text": "Avoid linen, actually only in summer"}
    )
    assert patch["source"] == "user"


def test_text_edit_on_user_pref_keeps_ownership_untouched():
    patch = apply_promotion("user", {"text": "Prefer monochrome"})
    assert "source" not in patch


def test_status_only_patch_does_not_promote():
    # Un-rejecting an inferred pref isn't an edit — the weekly job may still
    # refine it.
    patch = apply_promotion("inferred", {"status": "active"})
    assert "source" not in patch


def test_promotion_does_not_mutate_input_patch():
    original = {"text": "x"}
    apply_promotion("inferred", original)
    assert original == {"text": "x"}


# --- delete_disposition (#62 contract: tombstone inferred, delete user) ---


def test_inferred_pref_is_tombstoned():
    assert delete_disposition("inferred") == "tombstone"


def test_user_pref_is_hard_deleted():
    assert delete_disposition("user") == "delete"
