"""One-off backfill of clothing_items.warmth from metadata (issue #40).

Infers warmth 1-5 from type + fabric + name + description ONLY — no photo
re-reads; metadata is sufficient and free. Fill-nulls-only: rows with warmth
already set are never selected, let alone overwritten, so hand-set values
stick. Safe to re-run (each run only sees what's still null).

Run from repo root, after the 2026-06-10_clothing_warmth.sql migration:

    uv --project backend run python jobs/backfill_warmth.py            # writes
    uv --project backend run python jobs/backfill_warmth.py --dry-run  # prints only
"""

import json
import sys
from pathlib import Path

# Make `services`, `db`, etc. importable when run as `python jobs/backfill_warmth.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from db.supabase import client as supabase  # noqa: E402
from services.claude import MODEL, WARMTH_SCALE, client, parse_json  # noqa: E402

BACKFILL_SYSTEM_PROMPT = f"""You assign warmth ratings to clothing items from
their metadata (no photos). For each item in the user's JSON list, infer:

{WARMTH_SCALE}

Judge from type, fabric, name, and description. Return ONLY a JSON object
mapping each item's id to its warmth value (integer 1-5, or null for items
that don't affect warmth). Include every input id exactly once. No commentary,
no markdown fences. The JSON must be parseable.
"""


def main() -> int:
    dry_run = "--dry-run" in sys.argv

    rows = (
        supabase()
        .table("clothing_items")
        .select("id, name, type, fabric, description")
        .is_("warmth", "null")
        .execute()
        .data
        or []
    )
    if not rows:
        print("[done] no items with null warmth — nothing to backfill")
        return 0
    print(f"[run] inferring warmth for {len(rows)} items (metadata only)")

    resp = client().messages.create(
        model=MODEL,
        max_tokens=4096,
        system=BACKFILL_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": json.dumps(rows, ensure_ascii=False)}],
    )
    assignments = clean_assignments(rows, parse_json(resp))

    names = {row["id"]: row["name"] for row in rows}
    for iid, warmth in sorted(assignments.items(), key=lambda kv: kv[1]):
        print(f"  {warmth}  {names[iid]}")
    skipped = len(rows) - len(assignments)
    if skipped:
        print(f"[note] {skipped} item(s) left null (no-warmth items or missing from reply)")

    if dry_run:
        print(f"[dry-run] would set warmth on {len(assignments)} items; nothing written")
        return 0

    for iid, warmth in assignments.items():
        supabase().table("clothing_items").update({"warmth": warmth}).eq("id", iid).execute()
    print(f"[done] warmth set on {len(assignments)} items")
    return 0


def clean_assignments(rows: list[dict], raw: dict) -> dict[str, int]:
    """Pure: keep only valid (known id → int 1-5) assignments from the reply.

    Nulls (genuinely warmth-irrelevant items), hallucinated ids, and
    out-of-range values are all dropped — an unfilled row just stays null,
    which downstream code must tolerate anyway.
    """
    known = {row["id"] for row in rows}
    return {
        iid: warmth
        for iid, warmth in raw.items()
        if iid in known and isinstance(warmth, int) and 1 <= warmth <= 5
    }


if __name__ == "__main__":
    sys.exit(main())
