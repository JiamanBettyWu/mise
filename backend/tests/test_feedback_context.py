"""Tests for the recent-feedback prompt context (#59).

Pure helpers only — no Supabase / Claude calls: _select_feedback_entries
(outfit_history) shapes verdict rows into entries, _feedback_block (claude)
renders them into the prompt section the system prompt's feedback bullet
refers to.
"""

from services.claude import _feedback_block
from services.outfit_history import (
    FEEDBACK_CONTEXT_MAX_PER_VERDICT,
    _select_feedback_entries,
)

NAMES = {
    "a": "Linen blazer",
    "b": "Pleated trousers",
    "c": "Sport sandals",
    "d": "Silk blouse",
}


def row(on, mode, ids, verdict, **attribution):
    return {
        "recommended_on": on,
        "mode": mode,
        "item_ids": ids,
        "feedback": verdict,
        **attribution,
    }


# --- _select_feedback_entries ---


def test_select_shapes_and_hydrates_names():
    entries = _select_feedback_entries(
        [row("2026-06-07", "Elevated", ["a", "b", "c"], -1)], NAMES
    )
    assert entries == [
        {
            "date": "2026-06-07",
            "mode": "Elevated",
            "verdict": -1,
            "item_names": ["Linen blazer", "Pleated trousers", "Sport sandals"],
            "reason": None,
            "note": None,
        }
    ]


def test_select_caps_each_polarity_independently():
    # 7 dislikes + 2 likes, newest first: dislikes capped at the max, both
    # likes kept — the cap is per polarity, not global.
    rows = [row(f"2026-06-{10 - i:02d}", "Elevated", ["a"], -1) for i in range(7)]
    rows += [row("2026-06-02", "Smart casual", ["d"], 1)] * 2
    entries = _select_feedback_entries(rows, NAMES)
    dislikes = [e for e in entries if e["verdict"] == -1]
    likes = [e for e in entries if e["verdict"] == 1]
    assert len(dislikes) == FEEDBACK_CONTEXT_MAX_PER_VERDICT
    assert len(likes) == 2
    # Rows arrive newest-first, so the cap keeps the most recent ones.
    assert [e["date"] for e in dislikes] == [
        "2026-06-10", "2026-06-09", "2026-06-08", "2026-06-07", "2026-06-06",
    ]


def test_select_skips_deleted_items_and_drops_empty_entries():
    rows = [
        row("2026-06-07", "Elevated", ["a", "ghost"], -1),  # partial survives
        row("2026-06-06", "Athleisure", ["ghost"], -1),  # nothing left → dropped
    ]
    entries = _select_feedback_entries(rows, NAMES)
    assert len(entries) == 1
    assert entries[0]["item_names"] == ["Linen blazer"]


def test_select_ignores_non_verdict_rows():
    # Defensive, same as _feedback_multipliers: the fetch filters NULLs, but
    # a 0 or malformed value must not leak into the prompt.
    rows = [
        row("2026-06-07", "Elevated", ["a"], 0),
        row("2026-06-07", "Elevated", ["a"], None),
        row("2026-06-07", "Elevated", None, -1),
    ]
    assert _select_feedback_entries(rows, NAMES) == []


def test_select_drops_weather_attributed_dislikes():
    # #60: a 👎 attributed to the weather call is about the forecast, not the
    # outfit — it never reaches the prompt, and doesn't consume the cap.
    rows = [row("2026-06-07", "Elevated", ["a"], -1, feedback_reason="weather")]
    rows += [
        row(f"2026-06-{6 - i:02d}", "Elevated", ["b"], -1)
        for i in range(FEEDBACK_CONTEXT_MAX_PER_VERDICT)
    ]
    entries = _select_feedback_entries(rows, NAMES)
    assert len(entries) == FEEDBACK_CONTEXT_MAX_PER_VERDICT
    assert all(e["item_names"] == ["Pleated trousers"] for e in entries)


def test_select_specific_items_narrows_to_named_culprits():
    rows = [
        row(
            "2026-06-07",
            "Elevated",
            ["a", "b", "c"],
            -1,
            feedback_reason="specific_items",
            feedback_item_ids=["c"],
            feedback_note="hate these with anything dressy",
        )
    ]
    entries = _select_feedback_entries(rows, NAMES)
    assert entries[0]["item_names"] == ["Sport sandals"]
    assert entries[0]["reason"] == "specific_items"
    assert entries[0]["note"] == "hate these with anything dressy"


def test_select_likes_never_carry_attribution():
    # Attribution is 👎-only; stale fields on a flipped-to-👍 row (belt and
    # suspenders — the verdict write wipes them) must not leak through.
    rows = [
        row(
            "2026-06-07",
            "Smart casual",
            ["d"],
            1,
            feedback_reason="combination",
            feedback_note="stale",
        )
    ]
    entries = _select_feedback_entries(rows, NAMES)
    assert entries[0]["reason"] is None and entries[0]["note"] is None


# --- _feedback_block ---


def entry(verdict, mode="Elevated", date="2026-06-07", names=("Linen blazer",)):
    return {"date": date, "mode": mode, "verdict": verdict, "item_names": list(names)}


def test_block_renders_both_sections_dislikes_first():
    block = _feedback_block(
        [
            entry(1, mode="Smart casual", date="2026-06-08",
                  names=["Silk blouse", "Pleated trousers"]),
            entry(-1, names=["Linen blazer", "Sport sandals"]),
        ]
    )
    assert block == (
        "Recent outfit feedback:\n"
        "Disliked (avoid recombining similar assemblies):\n"
        "- Elevated, 2026-06-07: Linen blazer + Sport sandals\n"
        "Liked (style direction only — do not recreate these exact outfits):\n"
        "- Smart casual, 2026-06-08: Silk blouse + Pleated trousers"
    )


def test_block_omits_absent_polarity_sections():
    dislikes_only = _feedback_block([entry(-1)])
    assert "Disliked" in dislikes_only and "Liked" not in dislikes_only

    likes_only = _feedback_block([entry(1)])
    assert "Liked" in likes_only and "Disliked" not in likes_only


def test_block_renders_reason_tags_and_note():
    block = _feedback_block(
        [
            {**entry(-1, names=["Linen blazer", "Sport sandals"]),
             "reason": "combination", "note": "each fine alone, awful together"},
            {**entry(-1, mode="Athleisure", date="2026-06-06", names=["Silk blouse"]),
             "reason": "occasion"},
        ]
    )
    assert (
        "- Elevated, 2026-06-07: Linen blazer + Sport sandals "
        '(the combination, not the items) — user note: "each fine alone, awful together"'
    ) in block
    assert "- Athleisure, 2026-06-06: Silk blouse (wrong for this occasion/mode)" in block


def test_block_empty_entries_render_nothing():
    assert _feedback_block([]) == ""
