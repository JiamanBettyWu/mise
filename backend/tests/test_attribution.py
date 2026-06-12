"""Payload validation for record_attribution (#60).

Only the pre-DB raise paths: every check here fires before any Supabase
call, so the tests stay offline. The row-state guards (outfit not found,
verdict no longer 👎, named items outside the outfit) need the DB and are
exercised in production by the guarded update itself.
"""

import pytest

from services.outfit_history import AttributionError, record_attribution


def must_fail(status, reason=None, item_ids=(), note=""):
    with pytest.raises(AttributionError) as exc:
        record_attribution("hid", reason, list(item_ids), note)
    assert exc.value.status == status
    return str(exc.value)


def test_unknown_reason_rejected():
    assert "unknown reason" in must_fail(422, reason="vibes")


def test_empty_payload_rejected():
    assert "nothing to record" in must_fail(422)
    assert "nothing to record" in must_fail(422, note="   ")


def test_specific_items_requires_named_items():
    assert "at least one item" in must_fail(422, reason="specific_items")
