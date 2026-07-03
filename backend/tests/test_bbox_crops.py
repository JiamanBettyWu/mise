"""Tests for per-item crop thumbnails (#100).

Two layers, both offline:
- services.image: crop_to_bbox padding/clamping/fallbacks and
  fit_to_vision_limits shrink/no-op behavior, on tiny in-memory images.
- routers.clothes.upload_and_tag_multi: crop-vs-fallback URL wiring and the
  delete-original-when-unreferenced rule, with tagging/storage faked out.
"""

import asyncio
import io

import pytest
from PIL import Image

from routers import clothes
from services import image as image_svc


def _jpeg(width, height):
    img = Image.new("RGB", (width, height), "white")
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _size(data):
    return Image.open(io.BytesIO(data)).size


# ---- crop_to_bbox -----------------------------------------------------------


def test_crop_pads_each_edge_by_fraction_of_box():
    out = image_svc.crop_to_bbox(_jpeg(1000, 800), [100, 100, 300, 200], pad_frac=0.10)
    # box is 200x100; 10% padding adds 20px per x-edge, 10px per y-edge.
    assert _size(out) == (240, 120)


def test_crop_clamps_to_image_bounds():
    out = image_svc.crop_to_bbox(_jpeg(300, 200), [0, 0, 300, 200], pad_frac=0.10)
    assert _size(out) == (300, 200)


@pytest.mark.parametrize(
    "bbox",
    [
        None,
        [],
        [1, 2, 3],
        [1, 2, 3, 4, 5],
        "10,10,50,50",
        [50, 10, 10, 60],  # x2 <= x1
        [10, 60, 50, 60],  # y2 <= y1
        [10, "a", 50, 60],  # non-numeric
        [-500, -500, -400, -400],  # entirely out of frame
    ],
)
def test_crop_returns_none_for_unusable_boxes(bbox):
    assert image_svc.crop_to_bbox(_jpeg(300, 200), bbox) is None


def test_crop_output_is_jpeg():
    out = image_svc.crop_to_bbox(_jpeg(300, 200), [10, 10, 100, 100])
    assert Image.open(io.BytesIO(out)).format == "JPEG"


# ---- fit_to_vision_limits ---------------------------------------------------


def test_fit_noop_when_already_under_limits():
    data = _jpeg(800, 600)
    out, mime = image_svc.fit_to_vision_limits(data, "image/jpeg")
    assert out is data
    assert mime == "image/jpeg"


def test_fit_shrinks_long_edge():
    out, mime = image_svc.fit_to_vision_limits(_jpeg(4000, 1000), "image/jpeg")
    w, h = _size(out)
    assert max(w, h) <= image_svc.VISION_MAX_EDGE
    assert mime == "image/jpeg"


def test_fit_shrinks_megapixels():
    # 1500x1500 is under the 1568 edge cap but over 1.15 MP.
    out, _ = image_svc.fit_to_vision_limits(_jpeg(1500, 1500), "image/jpeg")
    w, h = _size(out)
    assert w * h <= image_svc.VISION_MAX_PIXELS


def test_fit_is_idempotent():
    # The router and the tagging call both apply the fit; the second pass must
    # return the same bytes or their coordinate frames desync (#96).
    once, mime = image_svc.fit_to_vision_limits(_jpeg(4000, 3000), "image/jpeg")
    twice, _ = image_svc.fit_to_vision_limits(once, mime)
    assert twice is once


# ---- upload_and_tag_multi routing -------------------------------------------


class _FakeUpload:
    content_type = "image/jpeg"
    filename = "photo.jpg"

    async def read(self):
        return b"image-bytes"


def _tag(name, bbox):
    return {
        "name": name,
        "type": "accessory",
        "color": "black",
        "formality": "casual",
        "season": "all-season",
        "fabric": "leather",
        "warmth": None,
        "description": "",
        "brand": None,
        "bbox": bbox,
    }


@pytest.fixture
def multi_env(monkeypatch):
    """Fake out normalization, tagging, and storage; return the call ledger."""
    env = {"uploads": [], "deleted": [], "tags": []}

    def fake_upload(image_bytes, filename, mime_type, storage_path=None):
        path = storage_path or "orig.jpg"
        env["uploads"].append(path)
        return path, f"url:{path}"

    monkeypatch.setattr(clothes, "ensure_under_limit", lambda b, m: (b, m))
    monkeypatch.setattr(clothes, "fit_to_vision_limits", lambda b, m: (b, m))
    monkeypatch.setattr(clothes, "tag_clothing_photo_multi", lambda b, m: env["tags"])
    monkeypatch.setattr(clothes, "upload_photo", fake_upload)
    monkeypatch.setattr(clothes, "delete_photo", env["deleted"].append)
    monkeypatch.setattr(
        clothes, "crop_to_bbox", lambda b, bbox: b"crop" if bbox else None
    )
    return env


def test_all_good_boxes_upload_crops_and_delete_original(multi_env):
    multi_env["tags"] = [_tag("Belt", [1, 1, 2, 2]), _tag("Scarf", [3, 3, 4, 4])]

    out = asyncio.run(clothes.upload_and_tag_multi(_FakeUpload()))

    assert [s.photo_url for s in out] == ["url:orig_item0.jpg", "url:orig_item1.jpg"]
    assert multi_env["uploads"] == ["orig.jpg", "orig_item0.jpg", "orig_item1.jpg"]
    # No row references the shared original, so it must not linger in storage.
    assert multi_env["deleted"] == ["url:orig.jpg"]


def test_bad_box_falls_back_to_original_which_is_kept(multi_env):
    multi_env["tags"] = [_tag("Belt", [1, 1, 2, 2]), _tag("Scarf", None)]

    out = asyncio.run(clothes.upload_and_tag_multi(_FakeUpload()))

    assert out[0].photo_url == "url:orig_item0.jpg"
    assert out[1].photo_url == "url:orig.jpg"
    assert multi_env["deleted"] == []


def test_crop_exception_falls_back_not_fails(multi_env, monkeypatch):
    def boom(b, bbox):
        raise RuntimeError("pillow exploded")

    monkeypatch.setattr(clothes, "crop_to_bbox", boom)
    multi_env["tags"] = [_tag("Belt", [1, 1, 2, 2])]

    out = asyncio.run(clothes.upload_and_tag_multi(_FakeUpload()))

    assert out[0].photo_url == "url:orig.jpg"
    assert multi_env["deleted"] == []


def test_empty_tags_upload_nothing(multi_env):
    multi_env["tags"] = []

    out = asyncio.run(clothes.upload_and_tag_multi(_FakeUpload()))

    assert out == []
    assert multi_env["uploads"] == []
    assert multi_env["deleted"] == []


def test_tagging_failure_uploads_nothing(multi_env, monkeypatch):
    def boom(b, m):
        raise RuntimeError("api down")

    monkeypatch.setattr(clothes, "tag_clothing_photo_multi", boom)

    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        asyncio.run(clothes.upload_and_tag_multi(_FakeUpload()))
    assert multi_env["uploads"] == []
    assert multi_env["deleted"] == []
