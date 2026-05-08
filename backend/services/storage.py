import os
import uuid
from pathlib import PurePosixPath

from db.supabase import client

BUCKET = "clothes-photos"


def upload_photo(image_bytes: bytes, filename: str, mime_type: str) -> tuple[str, str]:
    """Upload an image to Supabase Storage. Returns (storage_path, public_url)."""
    ext = PurePosixPath(filename).suffix.lower() or _ext_from_mime(mime_type)
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
