import os
import uuid
from pathlib import PurePosixPath

from db.supabase import client

BUCKET = "clothes-photos"


def upload_photo(
    image_bytes: bytes,
    filename: str,
    mime_type: str,
    storage_path: str | None = None,
) -> tuple[str, str]:
    """Upload an image to Supabase Storage. Returns (storage_path, public_url).

    `storage_path` overrides the generated name — used by per-item crops
    (#100) to land as siblings of their shared original ({stem}_item{i}.jpg).
    """
    if storage_path is None:
        # Prefer the mime type for the extension so the file path matches the
        # actual bytes — e.g. when HEIC was transcoded to JPEG upstream, we
        # want ".jpg", not the original ".heic" the user uploaded.
        ext = _ext_from_mime(mime_type) or PurePosixPath(filename).suffix.lower()
        storage_path = f"{uuid.uuid4()}{ext}"

    client().storage.from_(BUCKET).upload(
        path=storage_path,
        file=image_bytes,
        file_options={"content-type": mime_type, "upsert": "false"},
    )

    base = os.environ["SUPABASE_URL"].rstrip("/")
    public_url = f"{base}/storage/v1/object/public/{BUCKET}/{storage_path}"
    return storage_path, public_url


def delete_photo(public_url: str) -> None:
    """Best-effort delete; ignores missing objects."""
    marker = f"/storage/v1/object/public/{BUCKET}/"
    if marker not in public_url:
        return
    storage_path = public_url.split(marker, 1)[1]
    try:
        client().storage.from_(BUCKET).remove([storage_path])
    except Exception:
        pass


def _ext_from_mime(mime: str) -> str:
    return {
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/heic": ".heic",
    }.get(mime, "")
