import io

from PIL import Image
from pillow_heif import register_heif_opener

register_heif_opener()

MAX_DIM = 1600
JPEG_QUALITY = 85
# Anthropic's 5 MB limit is on the base64-encoded payload (4/3 inflation),
# so cap raw bytes at ~3.5 MB to keep encoded size safely under 5 MB.
TARGET_BYTES = 3_500_000


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


def _exif_transpose(img: Image.Image) -> Image.Image:
    try:
        from PIL import ImageOps
        return ImageOps.exif_transpose(img)
    except Exception:
        return img
