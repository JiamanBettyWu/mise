"""Tests for the recently-recommended prompt context (#135).

Pure/frozen paths only — no Supabase / Claude calls: recent_picks with
injected rows + names (the same offline-eval seam as the other history
helpers), and _recent_picks_block rendering.
"""

from datetime import date

from services.claude import _recent_picks_block
from services.outfit_history import recent_picks

TODAY = date(2026, 7, 9)
NAMES = {
    "a": "Shady blue satin maxi skirt",
    "b": "Lavender satin midi bias skirt",
    "c": "White linen shirt",
}


def row(on, ids, mode="Smart casual"):
    return {"recommended_on": on, "mode": mode, "item_ids": ids}


# --- recent_picks (frozen seam) ---


def test_dedupes_to_most_recent_occurrence_sorted_by_recency():
    picks = recent_picks(
        today=TODAY,
        rows=[
            row("2026-07-05", ["a", "c"]),
            row("2026-07-08", ["a"]),
            row("2026-07-07", ["b"]),
        ],
        names_by_id=NAMES,
    )
    assert picks == [
        {"name": "Shady blue satin maxi skirt", "days_ago": 1},
        {"name": "Lavender satin midi bias skirt", "days_ago": 2},
        {"name": "White linen shirt", "days_ago": 4},
    ]


def test_windows_out_old_rows_and_skips_unknown_ids():
    picks = recent_picks(
        today=TODAY,
        rows=[
            row("2026-06-20", ["a"]),  # outside HISTORY_WINDOW_DAYS
            row("2026-07-08", ["zzz", "c"]),  # zzz not in catalog (deleted)
        ],
        names_by_id=NAMES,
    )
    assert picks == [{"name": "White linen shirt", "days_ago": 1}]


def test_empty_rows_give_empty_picks():
    assert recent_picks(today=TODAY, rows=[], names_by_id=NAMES) == []


# --- _recent_picks_block ---


def test_block_renders_names_with_days_ago():
    block = _recent_picks_block(
        [
            {"name": "Shady blue satin maxi skirt", "days_ago": 0},
            {"name": "White linen shirt", "days_ago": 3},
        ]
    )
    assert block.splitlines() == [
        "Recently recommended items (prefer pieces NOT on this list):",
        "- Shady blue satin maxi skirt (today)",
        "- White linen shirt (3d ago)",
    ]


def test_block_empty_picks_render_nothing():
    assert _recent_picks_block([]) == ""
