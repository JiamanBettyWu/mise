"""Tests for the orphaned-photo sweep's pure decision logic (issue #102).

find_orphans is the only part worth unit-testing here -- list_all_objects/
referenced_paths/main are thin I/O wrappers around the Supabase client.
"""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "jobs"))

from sweep_orphaned_photos import find_orphans  # noqa: E402

NOW = datetime(2026, 7, 3, tzinfo=timezone.utc)


def _obj(name, hours_old=None):
    obj = {"name": name}
    if hours_old is not None:
        created = NOW - timedelta(hours=hours_old)
        obj["created_at"] = created.isoformat().replace("+00:00", "Z")
    return obj


def test_referenced_object_is_never_orphaned_even_when_old():
    objects = [_obj("a.jpg", hours_old=1000)]
    assert find_orphans(objects, {"a.jpg"}, NOW) == []


def test_unreferenced_object_past_age_floor_is_orphaned():
    objects = [_obj("a.jpg", hours_old=25)]
    assert find_orphans(objects, set(), NOW) == ["a.jpg"]


def test_unreferenced_object_within_age_floor_is_protected():
    objects = [_obj("a.jpg", hours_old=1)]
    assert find_orphans(objects, set(), NOW) == []


def test_missing_created_at_is_skipped_not_deleted():
    objects = [_obj("a.jpg")]
    assert find_orphans(objects, set(), NOW) == []


def test_mixed_batch_only_flags_the_true_orphan():
    objects = [
        _obj("referenced.jpg", hours_old=1000),
        _obj("fresh.jpg", hours_old=1),
        _obj("orphan.jpg", hours_old=48),
    ]
    assert find_orphans(objects, {"referenced.jpg"}, NOW) == ["orphan.jpg"]
