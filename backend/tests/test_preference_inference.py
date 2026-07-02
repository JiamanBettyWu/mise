"""Pure tests for the #62 weekly preference-inference graph.

No Supabase / Claude calls: every node's logic that *matters* is in the pure
helpers — shaping verdict rows, rendering them as citeable lines, the
evidence-count gate, and validate_node's index→id mapping + drop rules. Those
drop rules are the load-bearing safety: validate is the only thing standing
between a sloppy model and (a) a single-data-point "preference" or (b) a
resurrected tombstone the user already dismissed.
"""

from services.preference_inference import (
    MIN_EVIDENCE_PER_STATEMENT,
    MIN_VERDICTS,
    _build_inference_prompt,
    _normalize,
    _shape_verdicts,
    _validate_inferred,
    _verdict_line,
    _weather_phrase,
    check_evidence,
)

# --- _shape_verdicts ---


def _row(**over):
    base = {
        "id": "r1",
        "recommended_on": "2026-06-05",
        "mode": "Elevated",
        "item_ids": ["a", "b"],
        "feedback": -1,
        "feedback_reason": "combination",
        "feedback_item_ids": None,
        "feedback_note": "  too sporty  ",
        "weather": {"temp_high_c": 24, "temp_low_c": 14, "conditions": "clear"},
        "notes": None,
    }
    base.update(over)
    return base


NAMES = {"a": "Black blazer", "b": "Sport sandals", "c": "White tee"}


def test_shape_hydrates_names_and_strips_note():
    [v] = _shape_verdicts([_row()], NAMES)
    assert v["item_names"] == ["Black blazer", "Sport sandals"]
    assert v["note"] == "too sporty"  # whitespace stripped
    assert v["verdict"] == -1
    assert v["id"] == "r1"


def test_shape_skips_non_pm1_verdicts():
    rows = [_row(feedback=0), _row(feedback=None), _row(feedback=1)]
    shaped = _shape_verdicts(rows, NAMES)
    assert [v["verdict"] for v in shaped] == [1]


def test_shape_drops_deleted_item_names_but_keeps_row():
    [v] = _shape_verdicts([_row(item_ids=["a", "gone"])], NAMES)
    assert v["item_names"] == ["Black blazer"]  # 'gone' has no name, dropped


def test_shape_blank_note_becomes_none():
    [v] = _shape_verdicts([_row(feedback_note="   ")], NAMES)
    assert v["note"] is None


def test_shape_preserves_input_order():
    rows = [_row(id="r1"), _row(id="r2"), _row(id="r3")]
    assert [v["id"] for v in _shape_verdicts(rows, NAMES)] == ["r1", "r2", "r3"]


# --- _weather_phrase ---


def test_weather_phrase_renders_temps_and_conditions():
    assert (
        _weather_phrase({"temp_high_c": 24, "temp_low_c": 14, "conditions": "clear"})
        == "24/14°C, clear"
    )


def test_weather_phrase_handles_missing_and_malformed():
    assert _weather_phrase(None) == ""
    assert _weather_phrase("not a dict") == ""
    assert _weather_phrase({}) == ""
    assert _weather_phrase({"conditions": "rain"}) == "rain"


# --- _verdict_line ---


def test_verdict_line_has_index_thumb_items_reason_weather_note():
    [v] = _shape_verdicts([_row()], NAMES)
    line = _verdict_line(3, v)
    assert line.startswith("[3] 👎 disliked")
    assert "Black blazer + Sport sandals" in line
    assert "reason: combination" in line
    assert "weather: 24/14°C, clear" in line
    assert 'note: "too sporty"' in line


def test_verdict_line_thumb_up_and_no_items_placeholder():
    [v] = _shape_verdicts(
        [_row(feedback=1, item_ids=["gone"], feedback_note=None)], NAMES
    )
    line = _verdict_line(1, v)
    assert "👍 liked" in line
    assert "(items no longer in catalog)" in line


# --- _normalize ---


def test_normalize_casefolds_collapses_ws_and_strips_trailing_punct():
    assert _normalize("  Avoid   LINEN.  ") == "avoid linen"
    assert _normalize("Prefer monochrome!!") == "prefer monochrome"
    assert _normalize("avoid linen") == _normalize("Avoid Linen.")


# --- check_evidence (the cold-start gate) ---


def test_check_evidence_below_floor_is_insufficient():
    state = {"verdicts": [{}] * (MIN_VERDICTS - 1)}
    assert check_evidence(state) == "insufficient"


def test_check_evidence_at_floor_is_sufficient():
    state = {"verdicts": [{}] * MIN_VERDICTS}
    assert check_evidence(state) == "sufficient"


def test_check_evidence_empty_is_insufficient():
    assert check_evidence({}) == "insufficient"


# --- _validate_inferred (index→id mapping + drop rules) ---


def _verdicts(n):
    return [{"id": f"r{i}"} for i in range(1, n + 1)]


def test_validate_maps_indices_to_ids():
    verdicts = _verdicts(5)
    [out] = _validate_inferred(
        [{"text": "Likes monochrome", "evidence": [1, 3, 5]}],
        verdicts=verdicts,
        rejected=[],
        existing_user=[],
    )
    assert out == {"text": "Likes monochrome", "evidence_ids": ["r1", "r3", "r5"]}


def test_validate_drops_statement_below_evidence_floor():
    verdicts = _verdicts(5)
    out = _validate_inferred(
        [{"text": "Thin pattern", "evidence": [1, 2]}],  # only 2 < 3
        verdicts=verdicts,
        rejected=[],
        existing_user=[],
    )
    assert out == []


def test_validate_dedupes_repeated_indices_before_counting():
    # Three citations but only two distinct rows → below the floor → dropped.
    verdicts = _verdicts(5)
    out = _validate_inferred(
        [{"text": "x", "evidence": [1, 1, 2]}],
        verdicts=verdicts,
        rejected=[],
        existing_user=[],
    )
    assert out == []


def test_validate_drops_out_of_range_and_non_int_indices():
    verdicts = _verdicts(3)
    # 99 is out of range, "two" non-int → only 1,2,3 survive (exactly the floor)
    [out] = _validate_inferred(
        [{"text": "ok", "evidence": [1, 2, 3, 99, "two"]}],
        verdicts=verdicts,
        rejected=[],
        existing_user=[],
    )
    assert out["evidence_ids"] == ["r1", "r2", "r3"]


def test_validate_drops_rejected_tombstone_collision():
    verdicts = _verdicts(5)
    out = _validate_inferred(
        [{"text": "Avoid linen.", "evidence": [1, 2, 3]}],
        verdicts=verdicts,
        rejected=["avoid linen"],  # normalized match
        existing_user=[],
    )
    assert out == []


def test_validate_drops_existing_user_pref_restatement():
    verdicts = _verdicts(5)
    out = _validate_inferred(
        [{"text": "Prefer Monochrome", "evidence": [1, 2, 3]}],
        verdicts=verdicts,
        rejected=[],
        existing_user=["prefer monochrome"],
    )
    assert out == []


def test_validate_drops_empty_text():
    verdicts = _verdicts(5)
    out = _validate_inferred(
        [{"text": "   ", "evidence": [1, 2, 3]}],
        verdicts=verdicts,
        rejected=[],
        existing_user=[],
    )
    assert out == []


def test_validate_keeps_multiple_valid_and_drops_invalid_together():
    verdicts = _verdicts(6)
    out = _validate_inferred(
        [
            {"text": "Likes earth tones", "evidence": [1, 2, 3]},
            {"text": "weak", "evidence": [4]},  # dropped: 1 < 3
            {"text": "Avoids heels for casual", "evidence": [4, 5, 6]},
        ],
        verdicts=verdicts,
        rejected=[],
        existing_user=[],
    )
    assert [o["text"] for o in out] == ["Likes earth tones", "Avoids heels for casual"]


# --- _build_inference_prompt ---


def test_prompt_numbers_verdicts_and_includes_context_sections():
    verdicts = _shape_verdicts([_row(id="r1"), _row(id="r2", feedback=1)], NAMES)
    prompt = _build_inference_prompt(
        verdicts,
        existing_user=["Prefer monochrome"],
        rejected=["Avoid linen"],
    )
    assert "[1] 👎 disliked" in prompt
    assert "[2] 👍 liked" in prompt
    assert "Already known" in prompt and "Prefer monochrome" in prompt
    assert "Previously dismissed" in prompt and "Avoid linen" in prompt


def test_prompt_omits_context_sections_when_empty():
    verdicts = _shape_verdicts([_row()], NAMES)
    prompt = _build_inference_prompt(verdicts, existing_user=[], rejected=[])
    assert "Already known" not in prompt
    assert "Previously dismissed" not in prompt
