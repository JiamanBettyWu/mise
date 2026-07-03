import asyncio

from routers import clothes
from schemas import TagSuggestion


class _FakeUpload:
    content_type = "image/jpeg"
    filename = "photo.jpg"

    async def read(self):
        return b"image-bytes"


def test_single_upload_no_item_deletes_photo_and_returns_empty_list(monkeypatch):
    deleted = []

    monkeypatch.setattr(clothes, "ensure_under_limit", lambda b, m: (b, m))
    monkeypatch.setattr(
        clothes, "upload_photo", lambda b, filename, mime_type: ("path", "public-url")
    )
    monkeypatch.setattr(clothes, "tag_clothing_photo", lambda b, m: None)
    monkeypatch.setattr(clothes, "delete_photo", deleted.append)

    out = asyncio.run(clothes.upload_and_tag(_FakeUpload()))

    assert out == []
    assert deleted == ["public-url"]


def test_single_upload_item_returns_suggestion(monkeypatch):
    deleted = []

    monkeypatch.setattr(clothes, "ensure_under_limit", lambda b, m: (b, m))
    monkeypatch.setattr(
        clothes, "upload_photo", lambda b, filename, mime_type: ("path", "public-url")
    )
    monkeypatch.setattr(
        clothes,
        "tag_clothing_photo",
        lambda b, m: {
            "name": "Black leather belt",
            "type": "belt",
            "color": "black",
            "formality": "smart-casual",
            "season": "all-season",
            "fabric": "leather",
            "warmth": None,
            "description": "Slim black belt with silver hardware.",
            "brand": None,
        },
    )
    monkeypatch.setattr(clothes, "delete_photo", deleted.append)

    out = asyncio.run(clothes.upload_and_tag(_FakeUpload()))

    assert isinstance(out, TagSuggestion)
    assert out.photo_url == "public-url"
    assert out.name == "Black leather belt"
    assert deleted == []
