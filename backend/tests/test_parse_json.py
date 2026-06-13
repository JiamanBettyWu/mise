"""Tests for claude.parse_json / _extract_json tolerance.

Regression for the first live #62 run: Sonnet narrated its analysis in prose
and then emitted the JSON inside a ```json fence at the end. The old parser
only stripped a fence when the response *started* with ```, so json.loads
choked on the leading prose. parse_json is the shared chokepoint for every
pipeline, so the fix lives there.
"""

import pytest

from services.claude import _extract_json, parse_json


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResp:
    def __init__(self, text, stop_reason="end_turn"):
        self.content = [_FakeBlock(text)]
        self.stop_reason = stop_reason


# --- _extract_json (pure) ---


def test_plain_object_unchanged():
    assert _extract_json('{"a": 1}') == '{"a": 1}'


def test_strips_leading_prose_before_object():
    assert _extract_json('Here you go:\n{"a": 1}') == '{"a": 1}'


def test_prefers_fenced_block_after_prose():
    text = 'Let me think.\n\n```json\n{"preferences": []}\n```'
    assert _extract_json(text) == '{"preferences": []}'


def test_handles_bare_fence_without_language_tag():
    assert _extract_json('```\n{"a": 1}\n```') == '{"a": 1}'


def test_no_json_returns_text_for_diagnostics():
    assert _extract_json("nothing here") == "nothing here"


# --- parse_json (integration over the fake resp) ---


def test_parse_recovers_the_real_failure_shape():
    # Abridged from the actual failed Actions run: prose with markdown, then
    # the JSON in a trailing ```json fence.
    text = (
        "I need to find patterns with at least 3 supporting verdicts each.\n\n"
        "**Athleisure → liked:**\n- [4] ...\n- [7] ...\n\n"
        "I'll go with the cohesive athleisure pattern.\n\n"
        "```json\n"
        '{"preferences": [{"text": "Likes cohesive athleisure sets", '
        '"evidence": [4, 7, 8]}]}\n'
        "```"
    )
    assert parse_json(_FakeResp(text)) == {
        "preferences": [
            {"text": "Likes cohesive athleisure sets", "evidence": [4, 7, 8]}
        ]
    }


def test_parse_clean_object_still_works():
    assert parse_json(_FakeResp('{"outfits": []}')) == {"outfits": []}


def test_parse_raises_with_diagnostics_on_garbage():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_json(_FakeResp("not json at all", stop_reason="max_tokens"))
