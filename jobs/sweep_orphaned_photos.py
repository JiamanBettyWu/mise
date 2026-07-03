"""Sweep orphaned objects from the clothes-photos bucket (issue #102).

Multi-item review uploads storage objects at tag time but rows only get
created when a review card is committed. Abandoning the review (nav away, tab
close) leaves the uploaded object with nothing in clothing_items.photo_url
pointing at it -- the delete-time ref-count in routers/clothes.py never runs
because the object was never referenced in the first place. This job is the
backstop: list every object in the bucket, keep anything referenced OR younger
than the age floor (protects uploads mid-review), delete the rest. The bucket
only ever holds clothing photos, so referenced-or-recent is the whole
invariant -- nothing else needs excluding.

Run from repo root:

    uv --project backend run python jobs/sweep_orphaned_photos.py            # writes
    uv --project backend run python jobs/sweep_orphaned_photos.py --dry-run  # prints only
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Make `services`, `db`, etc. importable when run as `python jobs/sweep_orphaned_photos.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from db.supabase import client as supabase  # noqa: E402
from services.storage import BUCKET  # noqa: E402

AGE_FLOOR = timedelta(hours=24)
PAGE_SIZE = 100


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    referenced = referenced_paths()
    objects = list_all_objects()
    orphans = find_orphans(objects, referenced, datetime.now(timezone.utc))

    if not orphans:
        print(
            f"[done] no orphans found ({len(objects)} objects scanned, "
            f"{len(referenced)} referenced)"
        )
        return 0

    print(f"[run] {len(orphans)} orphaned object(s) older than {AGE_FLOOR}:")
    for name in orphans:
        print(f"  {name}")

    if dry_run:
        print(f"[dry-run] would delete {len(orphans)} object(s); nothing written")
        return 0

    supabase().storage.from_(BUCKET).remove(orphans)
    print(f"[done] deleted {len(orphans)} orphaned object(s)")
    return 0


def list_all_objects() -> list[dict]:
    """All objects in the bucket, paginated (list() caps at PAGE_SIZE per call)."""
    objects = []
    offset = 0
    while True:
        page = (
            supabase()
            .storage.from_(BUCKET)
            .list(options={"limit": PAGE_SIZE, "offset": offset})
        )
        if not page:
            break
        objects.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return objects


def referenced_paths() -> set[str]:
    """Storage paths (not full URLs) referenced by any clothing_items row.

    Paginated: PostgREST caps a bare .select() at 1000 rows, and silently
    truncating here would make live photos look orphaned to a delete job.
    """
    marker = f"/storage/v1/object/public/{BUCKET}/"
    rows = []
    offset = 0
    while True:
        page = (
            supabase()
            .table("clothing_items")
            .select("photo_url")
            .range(offset, offset + PAGE_SIZE - 1)
            .execute()
            .data
            or []
        )
        rows.extend(page)
        if len(page) < PAGE_SIZE:
            break
        offset += PAGE_SIZE
    return {
        row["photo_url"].split(marker, 1)[1]
        for row in rows
        if row["photo_url"] and marker in row["photo_url"]
    }


def find_orphans(objects: list[dict], referenced: set[str], now: datetime) -> list[str]:
    """Pure: object names that are unreferenced AND past the age floor.

    Objects with no created_at are skipped rather than deleted -- we can't
    prove they're past the age floor, and a false-positive delete is a lost
    photo while a false-negative just waits for the next sweep.
    """
    orphans = []
    for obj in objects:
        name = obj.get("name")
        if not name or name in referenced:
            continue
        created_at = obj.get("created_at")
        if not created_at:
            continue
        age = now - datetime.fromisoformat(created_at.replace("Z", "+00:00"))
        if age >= AGE_FLOOR:
            orphans.append(name)
    return orphans


if __name__ == "__main__":
    sys.exit(main())
