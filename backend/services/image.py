import io

from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

MAX_DIM = 1600
JPEG_QUALITY = 85
# Anthropic's 5 MB limit is on the base64-encoded payload (4/3 inflation),
# so cap raw bytes at ~3.5 MB to keep encoded size safely under 5 MB.
TARGET_BYTES = 3_500_000

# Anthropic vision API internal resize limits: images beyond either bound are
# downscaled server-side before the model sees them, which desyncs the model's
# bbox coordinate space from ours (#96). Stay under both so no hidden resize
# happens and model coordinates are pixel-identical to our bytes.
VISION_MAX_EDGE = 1568
VISION_MAX_PIXELS = 1_150_000

# Padding added to each bbox edge when cropping (#100): boxes on small dark
# accessories run wide but always contain the item, so generous padding is
# cosmetically fine and guards against tight edges.
BBOX_PAD_FRAC = 0.10


def ensure_under_limit(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """Return (bytes, mime) safely under Claude's 5MB image limit.

    Always normalizes to JPEG when resizing or transcoding (HEIC -> JPEG).
    """
    if mime_type != "image/heic" and len(image_bytes) <= TARGET_BYTES:
        return image_bytes, mime_type

    img = Image.open(io.BytesIO(image_bytes))
    img = _exif_transpose(img)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((MAX_DIM, MAX_DIM), Image.LANCZOS)

    quality = JPEG_QUALITY
    while True:
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=quality, optimize=True)
        data = buf.getvalue()
        if len(data) <= TARGET_BYTES or quality <= 50:
            return data, "image/jpeg"
        quality -= 10


def fit_to_vision_limits(image_bytes: bytes, mime_type: str) -> tuple[bytes, str]:
    """Shrink the image below the vision API's resize thresholds (#96).

    No-op if already under both bounds. Callers that crop by model-reported
    bbox coordinates MUST send these exact bytes to the model and crop these
    exact bytes — that identity is the whole point.
    """
    img = Image.open(io.BytesIO(image_bytes))
    w, h = img.size
    scale = min(
        1.0,
        VISION_MAX_EDGE / max(w, h),
        (VISION_MAX_PIXELS / (w * h)) ** 0.5,
    )
    if scale >= 1.0:
        return image_bytes, mime_type
    img = img.convert("RGB").resize(
        (int(w * scale), int(h * scale)), Image.Resampling.LANCZOS
    )
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return buf.getvalue(), "image/jpeg"


def crop_to_bbox(
    image_bytes: bytes, bbox, pad_frac: float = BBOX_PAD_FRAC
) -> bytes | None:
    """Crop a per-item thumbnail from a model-reported bbox (#100).

    `bbox` is [x1, y1, x2, y2] in pixel coordinates of `image_bytes`. Each
    edge is padded outward by `pad_frac` of the box's own dimension, then
    clamped to the image bounds. Returns JPEG bytes, or None when the box is
    missing, malformed, degenerate, or out of frame — callers fall back to
    the full photo rather than failing the upload.
    """
    if not (isinstance(bbox, (list, tuple)) and len(bbox) == 4):
        return None
    try:
        x1, y1, x2, y2 = (float(v) for v in bbox)
    except (TypeError, ValueError):
        return None
    if x2 <= x1 or y2 <= y1:
        return None

    img = Image.open(io.BytesIO(image_bytes))
    pad_x = (x2 - x1) * pad_frac
    pad_y = (y2 - y1) * pad_frac
    left = max(0, int(x1 - pad_x))
    top = max(0, int(y1 - pad_y))
    right = min(img.width, int(x2 + pad_x))
    bottom = min(img.height, int(y2 + pad_y))
    if right <= left or bottom <= top:
        return None

    crop = img.crop((left, top, right, bottom))
    if crop.mode not in ("RGB", "L"):
        crop = crop.convert("RGB")
    buf = io.BytesIO()
    crop.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def image_size(image_bytes: bytes) -> tuple[int, int]:
    """Return (width, height) in pixels."""
    return Image.open(io.BytesIO(image_bytes)).size


def _exif_transpose(img: Image.Image) -> Image.Image:
    try:
        from PIL import ImageOps

        return ImageOps.exif_transpose(img)
    except Exception:
        return img
