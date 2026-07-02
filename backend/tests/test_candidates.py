"""Tests for the two-stage-lite candidate selection (#63).

Pure-Python, no Supabase / Claude calls: _normalize_entries coerces model
output shapes, _select_candidates is the deterministic stage 2 — first
candidate that isn't a 👎-attributed combination and passes structural
validation (#46).
"""

from services.claude import _normalize_entries, _select_candidates

TYPES = {
    "tee": "t-shirt",
    "blouse": "blouse",
    "jeans": "jeans",
    "skirt": "skirt",
    "flats": "shoes",
    "sandals": "sandals",
}


def cand(*ids, reasoning="fine"):
    return {"item_ids": list(ids), "reasoning": reasoning}


def entry(label, *candidates):
    return {"label": label, "candidates": list(candidates)}


# --- _normalize_entries ---


def test_normalize_passes_candidates_shape_through():
    entries = _normalize_entries([entry("Elevated", cand("tee", "jeans"))])
    assert entries == [{"label": "Elevated", "candidates": [cand("tee", "jeans")]}]


def test_normalize_wraps_flat_pre63_shape():
    entries = _normalize_entries(
        [{"label": "Elevated", "item_ids": ["tee"], "reasoning": "old shape"}]
    )
    assert entries == [
        {
            "label": "Elevated",
            "candidates": [{"item_ids": ["tee"], "reasoning": "old shape"}],
        }
    ]


def test_normalize_drops_non_dict_candidates():
    entries = _normalize_entries(
        [{"label": "x", "candidates": ["junk", cand("tee"), None]}]
    )
    assert entries[0]["candidates"] == [cand("tee")]


# --- _select_candidates ---


def test_first_clean_candidate_wins():
    out = _select_candidates(
        [entry("Elevated", cand("blouse", "skirt", "flats"), cand("tee", "jeans"))],
        blocked_combos=set(),
        types_by_id=TYPES,
    )
    assert out == [
        {
            "label": "Elevated",
            "item_ids": ["blouse", "skirt", "flats"],
            "reasoning": "fine",
        }
    ]


def test_blocked_combo_rejected_next_candidate_selected():
    # The dress+sandals case: candidate 1 exactly matches a 👎-attributed
    # combination → candidate 2 is served. Order-insensitive (set match).
    blocked = {frozenset(["skirt", "sandals", "tee"])}
    out = _select_candidates(
        [
            entry(
                "Elevated",
                cand("tee", "sandals", "skirt"),
                cand("blouse", "skirt", "flats"),
            )
        ],
        blocked_combos=blocked,
        types_by_id=TYPES,
    )
    assert out[0]["item_ids"] == ["blouse", "skirt", "flats"]


def test_structurally_invalid_candidate_skipped_when_valid_one_exists():
    two_bottoms = cand("tee", "jeans", "skirt")
    out = _select_candidates(
        [entry("Smart casual", two_bottoms, cand("tee", "jeans", "flats"))],
        blocked_combos=set(),
        types_by_id=TYPES,
    )
    assert out[0]["item_ids"] == ["tee", "jeans", "flats"]


def test_invalid_candidate_kept_as_repair_fallback():
    # No candidate survives both checks → hand the first non-blocked one to
    # the downstream repair machinery (#46) instead of inventing a skip.
    two_bottoms = cand("tee", "jeans", "skirt")
    blocked = {frozenset(["tee", "jeans", "flats"])}
    out = _select_candidates(
        [entry("Smart casual", cand("tee", "jeans", "flats"), two_bottoms)],
        blocked_combos=blocked,
        types_by_id=TYPES,
    )
    assert out[0]["item_ids"] == ["tee", "jeans", "skirt"]


def test_all_candidates_blocked_becomes_skip_entry():
    blocked = {frozenset(["tee", "jeans"]), frozenset(["blouse", "skirt"])}
    out = _select_candidates(
        [entry("Elevated", cand("tee", "jeans"), cand("blouse", "skirt"))],
        blocked_combos=blocked,
        types_by_id=TYPES,
    )
    assert out[0]["item_ids"] == []
    # Must match the skip convention recommend._is_skip anchors on.
    r = out[0]["reasoning"].lower()
    assert r.startswith("no ") and "recommendation available" in r


def test_recent_repeat_rejected_next_candidate_selected():
    # #17: yesterday's exact set is deduped; a fresh candidate is served.
    recent = {frozenset(["tee", "jeans", "flats"])}
    out = _select_candidates(
        [
            entry(
                "Smart casual",
                cand("flats", "tee", "jeans"),
                cand("blouse", "skirt", "flats"),
            )
        ],
        blocked_combos=set(),
        types_by_id=TYPES,
        recent_combos=recent,
    )
    assert out[0]["item_ids"] == ["blouse", "skirt", "flats"]


def test_all_repeats_serves_repeat_not_skip():
    # Unlike 👎-blocked combos, a repeat is annoying but wearable — when
    # every candidate is a repeat, serve one instead of skipping the mode.
    recent = {
        frozenset(["tee", "jeans", "flats"]),
        frozenset(["blouse", "skirt", "flats"]),
    }
    out = _select_candidates(
        [
            entry(
                "Smart casual",
                cand("tee", "jeans", "flats"),
                cand("blouse", "skirt", "flats"),
            )
        ],
        blocked_combos=set(),
        types_by_id=TYPES,
        recent_combos=recent,
    )
    assert out[0]["item_ids"] == ["tee", "jeans", "flats"]


def test_blocked_combo_never_served_even_when_only_alternative_is_repeat():
    blocked = {frozenset(["blouse", "skirt", "flats"])}
    recent = {frozenset(["tee", "jeans", "flats"])}
    out = _select_candidates(
        [
            entry(
                "Smart casual",
                cand("blouse", "skirt", "flats"),
                cand("tee", "jeans", "flats"),
            )
        ],
        blocked_combos=blocked,
        types_by_id=TYPES,
        recent_combos=recent,
    )
    # The 👎-blocked set stays buried; the repeat is the lesser evil.
    assert out[0]["item_ids"] == ["tee", "jeans", "flats"]


def test_repairable_fresh_candidate_preferred_over_repeat():
    # Severity order: a fresh outfit needing structural repair beats
    # serving a repeat outright.
    two_bottoms = cand("tee", "jeans", "skirt")
    recent = {frozenset(["tee", "jeans", "flats"])}
    out = _select_candidates(
        [entry("Smart casual", cand("tee", "jeans", "flats"), two_bottoms)],
        blocked_combos=set(),
        types_by_id=TYPES,
        recent_combos=recent,
    )
    assert out[0]["item_ids"] == ["tee", "jeans", "skirt"]


def test_model_skip_entry_passes_through():
    skip = cand(
        reasoning="No Elevated recommendation available today — nothing dressy."
    )
    out = _select_candidates(
        [entry("Elevated", skip)], blocked_combos=set(), types_by_id=TYPES
    )
    assert out[0]["item_ids"] == []
    assert "No Elevated recommendation" in out[0]["reasoning"]


def test_entries_keep_positions_and_labels():
    out = _select_candidates(
        [
            entry("Smart casual", cand("tee", "jeans", "flats")),
            entry("Athleisure", cand("tee", "jeans", "sandals")),
        ],
        blocked_combos=set(),
        types_by_id=TYPES,
    )
    assert [o["label"] for o in out] == ["Smart casual", "Athleisure"]
