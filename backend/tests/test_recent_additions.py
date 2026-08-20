"""Tests for the newly-added-items prompt context (#159).

Pure paths only — no Supabase / Claude calls: recent_additions over injected
pool rows (it reads `created_at` off the rows it is handed, so there is no
query to stub), and _recent_additions_block rendering.
"""

from datetime import date

from services.claude import _recent_additions_block
from services.outfit_history import NEW_ITEM_WINDOW_DAYS, recent_additions

TODAY = date(2026, 8, 19)


def item(iid, name, created_at):
    return {"id": iid, "name": name, "type": "top", "created_at": created_at}


# --- recent_additions (pure over the candidate pool) ---


def test_returns_window_items_newest_first():
    additions = recent_additions(
        [
            item("a", "Cream linen blazer", "2026-08-17T09:12:00+00:00"),
            item("b", "Black leather loafers", "2026-08-05T22:00:00+00:00"),
            item("c", "Old white tee", "2026-01-02T10:00:00+00:00"),
        ],
        today=TODAY,
    )
    assert additions == [
        {"name": "Cream linen blazer", "days_ago": 2},
        {"name": "Black leather loafers", "days_ago": 14},
    ]


def test_window_edge_is_inclusive_and_one_day_past_is_out():
    inside = f"{date(2026, 8, 19 - NEW_ITEM_WINDOW_DAYS).isoformat()}T00:00:00+00:00"
    outside = (
        f"{date(2026, 8, 19 - NEW_ITEM_WINDOW_DAYS - 1).isoformat()}T23:59:00+00:00"
    )
    additions = recent_additions(
        [item("a", "Edge item", inside), item("b", "Stale item", outside)],
        today=TODAY,
    )
    assert [a["name"] for a in additions] == ["Edge item"]


def test_missing_or_unusable_created_at_is_skipped_not_crashed():
    # The frozen eval catalogs (#118) carry only WARDROBE_FIELDS — no
    # created_at — so the eval path must degrade to "no new items".
    additions = recent_additions(
        [
            {"id": "a", "name": "Frozen eval item"},
            item("b", "Junk timestamp", "not-a-date"),
            item("c", "Null timestamp", None),
            item("d", "Unnamed", "2026-08-18T00:00:00+00:00") | {"name": ""},
        ],
        today=TODAY,
    )
    assert additions == []


def test_future_dated_rows_are_ignored():
    # Clock skew shouldn't produce a "-1d ago" line in the prompt.
    additions = recent_additions(
        [item("a", "Tomorrow's arrival", "2026-08-20T00:00:00+00:00")],
        today=TODAY,
    )
    assert additions == []


def test_date_objects_are_accepted():
    additions = recent_additions(
        [item("a", "Date-typed row", date(2026, 8, 18))], today=TODAY
    )
    assert additions == [{"name": "Date-typed row", "days_ago": 1}]


def test_empty_pool_gives_empty_additions():
    assert recent_additions([], today=TODAY) == []


# --- _recent_additions_block rendering ---


def test_block_renders_days_ago_with_today_special_case():
    block = _recent_additions_block(
        [
            {"name": "Cream linen blazer", "days_ago": 0},
            {"name": "Black leather loafers", "days_ago": 9},
        ]
    )
    assert block.splitlines() == [
        "Recently added to the wardrobe (she enjoys wearing new pieces):",
        "- Cream linen blazer (today)",
        "- Black leather loafers (added 9d ago)",
    ]


def test_empty_additions_render_nothing():
    assert _recent_additions_block([]) == ""


# --- inventory view (the created_at strip) ---


def testinventory_view_drops_created_at_and_keeps_everything_else():
    from services.recommend import inventory_view

    view = inventory_view([item("a", "Cream linen blazer", "2026-08-17T09:12:00Z")])
    assert view == [{"id": "a", "name": "Cream linen blazer", "type": "top"}]


def test_datetime_objects_are_narrowed_to_their_date():
    from datetime import datetime

    additions = recent_additions(
        [item("a", "Datetime-typed row", datetime(2026, 8, 18, 23, 30))], today=TODAY
    )
    assert additions == [{"name": "Datetime-typed row", "days_ago": 1}]
