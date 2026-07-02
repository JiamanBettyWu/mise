"""Tests for tag_clothing_photo_multi's response handling (#24).

The Anthropic client and image normalization are faked out; these cover the
parse/shape layer only — wrapper object vs bare array, empty result, the
MAX_MULTI_ITEMS cap, and malformed shapes.
"""

import json

import pytest

import services.claude as claude


class _FakeBlock:
    type = "text"

    def __init__(self, text):
        self.text = text


class _FakeResp:
    stop_reason = "end_turn"

    def __init__(self, text):
        self.content = [_FakeBlock(text)]


class _FakeClient:
    def __init__(self, text):
        self._text = text
        self.last_kwargs = None
        self.messages = self

    def create(self, **kwargs):
        self.last_kwargs = kwargs
        return _FakeResp(self._text)


@pytest.fixture
def fake_claude(monkeypatch):
    """Install a fake Anthropic client returning `text`; returns the fake."""

    def _install(text):
        fake = _FakeClient(text)
        monkeypatch.setattr(claude, "client", lambda: fake)
        monkeypatch.setattr(claude, "ensure_under_limit", lambda b, m: (b, m))
        return fake

    return _install


def _tags(n):
    return [{"name": f"Item {i}", "type": "accessory"} for i in range(n)]


def test_wrapped_items_object(fake_claude):
    fake_claude(json.dumps({"items": _tags(3)}))
    out = claude.tag_clothing_photo_multi(b"img", "image/jpeg")
    assert len(out) == 3
    assert out[0]["name"] == "Item 0"


def test_bare_array_tolerated(fake_claude):
    fake_claude(json.dumps(_tags(2)))
    assert len(claude.tag_clothing_photo_multi(b"img", "image/jpeg")) == 2


def test_empty_items_returns_empty_list(fake_claude):
    fake_claude('{"items": []}')
    assert claude.tag_clothing_photo_multi(b"img", "image/jpeg") == []


def test_truncates_to_max_items(fake_claude):
    fake_claude(json.dumps({"items": _tags(claude.MAX_MULTI_ITEMS + 3)}))
    out = claude.tag_clothing_photo_multi(b"img", "image/jpeg")
    assert len(out) == claude.MAX_MULTI_ITEMS


def test_non_list_items_raises(fake_claude):
    fake_claude('{"items": "nothing here"}')
    with pytest.raises(ValueError, match="Expected a list"):
        claude.tag_clothing_photo_multi(b"img", "image/jpeg")


def test_multi_call_gets_bigger_token_budget(fake_claude):
    # 9 items at the single-item 512 budget would truncate mid-JSON (#24).
    fake = fake_claude('{"items": []}')
    claude.tag_clothing_photo_multi(b"img", "image/jpeg")
    assert fake.last_kwargs["max_tokens"] >= 4096
