"""Offline tests for the recommender eval scorers + frozen-history seams (#118).

evals/recommend_scorers.py deliberately imports no weave, so the metric
functions are covered by the free suite — a buggy scorer would silently
corrupt every paid eval run. eval_recommend.py itself (weave + live Sonnet)
is exercised manually.

The second half covers the injected-rows paths in services/outfit_history:
with `rows`/`history_rows` given, the functions must be pure (no Supabase)
and must filter the same way the SQL does.
"""

import json
from datetime import date
from pathlib import Path

import pytest

from evals import recommend_scorers
from services import outfit_history
from services.outfit_history import (
    blocked_combos,
    recent_combos,
    recent_feedback_outfits,
    sample_wardrobe,
)

FIXTURES = json.loads(
    (
        Path(__file__).resolve().parents[1] / "evals" / "datasets" / "recommend.json"
    ).read_text()
)

# Minimal synthetic catalog: types drive the category logic.
CATALOG = [
    {"id": "tee", "name": "Tee", "type": "t-shirt", "warmth": 1},
    {"id": "shirt", "name": "Shirt", "type": "shirt", "warmth": 2},
    {"id": "jeans", "name": "Jeans", "type": "jeans", "warmth": 2},
    {"id": "skirt", "name": "Skirt", "type": "skirt", "warmth": 1},
    {"id": "dress", "name": "Dress", "type": "dress", "warmth": 2},
    {"id": "sneakers", "name": "Sneakers", "type": "sneakers", "warmth": 2},
    {"id": "sandals", "name": "Sandals", "type": "sandals", "warmth": 1},
    {"id": "coat", "name": "Down coat", "type": "coat", "warmth": 5},
]


def _output(*item_id_lists, labels=None):
    return {
        "outfits": [
            {"label": (labels or [""] * len(item_id_lists))[i], "item_ids": ids}
            for i, ids in enumerate(item_id_lists)
        ]
    }


# --- valid_structure ---


def test_structure_accepts_top_bottom_shoes():
    out = _output(["tee", "jeans", "sneakers"])
    assert recommend_scorers.valid_structure(out, CATALOG)["pass"]


def test_structure_accepts_dress_and_shoes():
    out = _output(["dress", "sneakers"])
    assert recommend_scorers.valid_structure(out, CATALOG)["pass"]


def test_structure_rejects_two_bottoms_and_dress_over_bottom():
    res = recommend_scorers.valid_structure(
        _output(["tee", "jeans", "skirt", "sneakers"]), CATALOG
    )
    assert not res["pass"] and "bottoms x2" in res["violations"][0]["problems"]
    res = recommend_scorers.valid_structure(
        _output(["dress", "jeans", "sneakers"]), CATALOG
    )
    assert not res["pass"] and "dress + bottom" in res["violations"][0]["problems"]


def test_structure_reports_missing_footwear_without_failing():
    # Omitting a slot is sanctioned by the prompt's EXCEPTION rule (#46):
    # reported as incomplete, never a pass failure.
    res = recommend_scorers.valid_structure(_output(["tee", "jeans"], []), CATALOG)
    assert res["pass"]
    assert res["incomplete_outfits"] == [""]
    assert res["skipped_modes"] == 1


def test_skipped_modes_alone_pass():
    assert recommend_scorers.valid_structure(_output([], []), CATALOG)["pass"]


# --- items_in_catalog ---


def test_items_in_catalog_flags_unknown_ids():
    res = recommend_scorers.items_in_catalog(
        _output(["tee", "ghost", "sneakers"]), CATALOG
    )
    assert not res["pass"] and res["unknown_ids"] == ["ghost"]


# --- no_gate_violations ---


def test_gate_scorer_vacuous_in_mild_weather():
    weather = {"temp_high_c": 18.0, "temp_low_c": 9.0}
    res = recommend_scorers.no_gate_violations(
        _output(["coat", "sandals"]), weather, CATALOG
    )
    assert res["pass"] and not res["applicable"]


def test_gate_scorer_flags_warmth5_in_heatwave():
    weather = {"temp_high_c": 35.0, "temp_low_c": 26.0}
    res = recommend_scorers.no_gate_violations(_output(["coat"]), weather, CATALOG)
    assert not res["pass"] and res["applicable"]


def test_gate_scorer_flags_sandals_in_deep_cold():
    weather = {"temp_high_c": -8.0, "temp_low_c": -15.0}
    res = recommend_scorers.no_gate_violations(_output(["sandals"]), weather, CATALOG)
    assert not res["pass"]
    # Warmth-1 non-footwear is layerable — never gated.
    res = recommend_scorers.no_gate_violations(_output(["skirt"]), weather, CATALOG)
    assert res["pass"]


# --- repeat_gap ---

TODAY = "2026-06-10"


def _history(*entries):
    return [
        {"recommended_on": d, "mode": "Smart casual", "item_ids": ids}
        for d, ids in entries
    ]


def _big_catalog():
    """Six tops so 'tops' exceeds SMALL_CATEGORY_MAX and gets repeat pressure."""
    tops = [
        {"id": f"top{i}", "name": f"Top {i}", "type": "shirt", "warmth": 2}
        for i in range(6)
    ]
    return CATALOG + tops


def test_repeat_gap_flags_early_large_category_repeat():
    hist = _history(("2026-06-09", ["top0"]))
    res = recommend_scorers.repeat_gap(_output(["top0"]), hist, _big_catalog(), TODAY)
    assert not res["pass"]
    assert "Top 0" in res["early_repeats"][0]
    assert res["min_gap_days"] == 1


def test_repeat_gap_exempts_small_categories_but_reports_them():
    hist = _history(("2026-06-09", ["sneakers"]))
    res = recommend_scorers.repeat_gap(
        _output(["sneakers"]), hist, _big_catalog(), TODAY
    )
    assert res["pass"], "footwear (small category) is exempt from the pass"
    assert res["footwear_min_gap_days"] == 1


def test_repeat_gap_fresh_items_and_old_repeats_pass():
    hist = _history(("2026-06-01", ["top0"]))
    res = recommend_scorers.repeat_gap(
        _output(["top0", "top1"]), hist, _big_catalog(), TODAY
    )
    assert res["pass"]
    assert res["fresh_fraction"] == 0.5
    assert res["mean_gap_days"] == 9


def test_repeat_gap_counts_intra_run_duplicates():
    res = recommend_scorers.repeat_gap(
        _output(["top0", "sneakers"], ["top0", "sandals"]), [], _big_catalog(), TODAY
    )
    assert res["intra_run_duplicates"] == 1


# --- frozen dataset sanity ---


def test_dataset_cases_reference_known_modes():
    mode_names = {m["name"] for m in FIXTURES["modes"]}
    for case in FIXTURES["cases"]:
        assert set(case["mode_names"]) <= mode_names
        assert {"temp_high_c", "temp_low_c", "conditions"} <= set(case["weather"])
        # Anchor must sit after the whole history window.
        assert all(r["recommended_on"] < case["today"] for r in FIXTURES["history"])


def test_dataset_history_has_no_default_mode_rows():
    assert all(r["mode"] != "(default)" for r in FIXTURES["history"])


# --- injected-rows seams in outfit_history (#118) ---


@pytest.fixture
def no_db(monkeypatch):
    """Any Supabase touch on the frozen path is a bug — make it loud."""

    def boom():
        raise AssertionError("frozen path must not touch Supabase")

    monkeypatch.setattr(outfit_history, "supabase", lambda: boom())


ROWS = [
    {
        "recommended_on": "2026-06-09",
        "mode": "Smart casual",
        "item_ids": ["a", "b"],
        "feedback": -1,
        "feedback_reason": "combination",
        "feedback_item_ids": None,
        "feedback_note": None,
    },
    {
        "recommended_on": "2026-06-08",
        "mode": "Athleisure",
        "item_ids": ["c"],
        "feedback": 1,
        "feedback_reason": None,
        "feedback_item_ids": None,
        "feedback_note": None,
    },
    {
        "recommended_on": "2026-05-01",  # outside every 7d window
        "mode": "Smart casual",
        "item_ids": ["old"],
        "feedback": None,
        "feedback_reason": None,
        "feedback_item_ids": None,
        "feedback_note": None,
    },
]


def test_blocked_combos_from_rows(no_db):
    assert blocked_combos(rows=ROWS) == {frozenset({"a", "b"})}


def test_recent_combos_from_rows_windows_and_anchors(no_db):
    combos = recent_combos(today=date(2026, 6, 10), rows=ROWS)
    assert combos == {frozenset({"a", "b"}), frozenset({"c"})}


def test_recent_feedback_outfits_from_rows(no_db):
    entries = recent_feedback_outfits(
        today=date(2026, 6, 10),
        rows=ROWS,
        names_by_id={"a": "A", "b": "B", "c": "C"},
    )
    assert [e["verdict"] for e in entries] == [-1, 1], "newest first"
    assert entries[0]["item_names"] == ["A", "B"]


def test_sample_wardrobe_with_history_rows_is_pure(no_db):
    wardrobe = [{"id": f"t{i}", "name": f"t{i}", "type": "shirt"} for i in range(8)] + [
        {"id": "a", "name": "a", "type": "shirt"}
    ]
    pool = sample_wardrobe(
        wardrobe,
        modes=[{"name": "Smart casual"}],
        today=date(2026, 6, 10),
        history_rows=ROWS,
    )
    assert pool, "sampling over frozen rows must still return a pool"
    assert {i["id"] for i in pool} <= {i["id"] for i in wardrobe}
