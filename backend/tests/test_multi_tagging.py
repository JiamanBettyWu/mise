"""Tests for tagging response handling (#24 plus single empty-state parity).

The Anthropic client and image normalization are faked out; these cover the
parse/shape layer only — wrapper object vs bare array, empty result, the
MAX_MULTI_ITEMS cap, single-item no-detection, and malformed shapes.
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
        monkeypatch.setattr(claude, "fit_to_vision_limits", lambda b, m: (b, m))
        monkeypatch.setattr(claude, "image_size", lambda b: (640, 480))
        return fake

    return _install


def _tags(n):
    return [{"name": f"Item {i}", "type": "accessory"} for i in range(n)]


def test_single_wrapped_item_returns_first_tag(fake_claude):
    fake_claude(json.dumps({"items": _tags(1)}))
    out = claude.tag_clothing_photo(b"img", "image/jpeg")
    assert out["name"] == "Item 0"


def test_single_empty_items_returns_none(fake_claude):
    fake_claude('{"items": []}')
    assert claude.tag_clothing_photo(b"img", "image/jpeg") is None


def test_single_legacy_object_tolerated(fake_claude):
    fake_claude(json.dumps({"name": "Legacy tag", "type": "accessory"}))
    out = claude.tag_clothing_photo(b"img", "image/jpeg")
    assert out["name"] == "Legacy tag"


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


def test_multi_bbox_passes_through(fake_claude):
    # #100: the router pops `bbox` for cropping; tagging must not strip it.
    tags = [{"name": "Belt", "type": "belt", "bbox": [10, 20, 110, 220]}]
    fake_claude(json.dumps({"items": tags}))
    out = claude.tag_clothing_photo_multi(b"img", "image/jpeg")
    assert out[0]["bbox"] == [10, 20, 110, 220]


def test_multi_prompt_states_image_dimensions(fake_claude):
    # #96: stating WxH anchors the bbox coordinate frame.
    fake = fake_claude('{"items": []}')
    claude.tag_clothing_photo_multi(b"img", "image/jpeg")
    text_blocks = [
        b["text"]
        for b in fake.last_kwargs["messages"][0]["content"]
        if b.get("type") == "text"
    ]
    assert any("640x480 pixels" in t for t in text_blocks)


def test_multi_call_gets_bigger_token_budget(fake_claude):
    # 9 items at the single-item 512 budget would truncate mid-JSON (#24).
    fake = fake_claude('{"items": []}')
    claude.tag_clothing_photo_multi(b"img", "image/jpeg")
    assert fake.last_kwargs["max_tokens"] >= 4096
