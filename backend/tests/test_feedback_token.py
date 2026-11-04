"""Tests for the signed feedback tokens (issue #39).

Pure-Python, no network. FEEDBACK_SECRET is pinned per-test via monkeypatch
(the real value from .env must never leak into assertions); expiry is tested
via the _now injection point rather than sleeping.
"""

import pytest

from services.feedback_token import (
    DEFAULT_TTL_DAYS,
    REFINE_KINDS,
    TokenError,
    sign_refine_token,
    sign_token,
    verify_refine_token,
    verify_token,
)

HID = "1f4a2b3c-0000-4000-8000-123456789abc"


@pytest.fixture(autouse=True)
def _pin_secret(monkeypatch):
    monkeypatch.setenv("FEEDBACK_SECRET", "test-secret-do-not-use")


def must_fail(token, _now=None):
    with pytest.raises(TokenError) as exc:
        verify_token(token, _now=_now)
    return str(exc.value)


def test_round_trip_both_verdicts():
    assert verify_token(sign_token(HID, 1)) == (HID, 1)
    assert verify_token(sign_token(HID, -1)) == (HID, -1)


def test_tokens_are_url_safe():
    token = sign_token(HID, 1)
    assert all(c.isalnum() or c in "-_." for c in token), token


def test_tampering_rejected():
    up, down = sign_token(HID, 1, _now=1000.0), sign_token(HID, -1, _now=1000.0)
    payload, sig = up.split(".")
    other_payload, _ = down.split(".")
    assert "signature" in must_fail(f"{other_payload}.{sig}")  # payload swap
    flipped = payload[:-1] + ("A" if payload[-1] != "A" else "B")
    assert must_fail(f"{flipped}.{sig}")  # single-char payload flip
    assert "malformed" in must_fail("not-a-token")
    assert "malformed" in must_fail("")
    assert "malformed" in must_fail("a.b.c.d")


def test_expiry_via_now_injection():
    t0 = 1_700_000_000.0
    token = sign_token(HID, 1, _now=t0)
    assert verify_token(token, _now=t0 + (DEFAULT_TTL_DAYS - 1) * 86400) == (HID, 1)
    assert "expired" in must_fail(token, _now=t0 + (DEFAULT_TTL_DAYS + 1) * 86400)


def test_wrong_or_missing_secret(monkeypatch):
    token = sign_token(HID, 1)
    monkeypatch.setenv("FEEDBACK_SECRET", "a-different-secret")
    assert "signature" in must_fail(token)
    monkeypatch.setenv("FEEDBACK_SECRET", "")
    assert "not configured" in must_fail(token)
    monkeypatch.setenv("FEEDBACK_SECRET", "test-secret-do-not-use")
    assert verify_token(token) == (HID, 1)  # restored secret works again


def test_invalid_verdicts_cannot_be_signed():
    with pytest.raises(ValueError):
        sign_token(HID, 0)


# ------------------------------------------------------------ refine tokens (#144)


def test_refine_round_trip_all_kinds():
    for kind in REFINE_KINDS:
        token = sign_refine_token(HID, kind)
        assert verify_refine_token(token) == (HID, kind)
        assert all(c.isalnum() or c in "-_." for c in token), token


def test_refine_kind_is_whitelisted():
    with pytest.raises(ValueError):
        sign_refine_token(HID, "add_hat")


def test_token_domains_are_disjoint():
    # A verdict token must never verify as a refine token or vice versa,
    # even though both are signed with the same secret.
    with pytest.raises(TokenError):
        verify_refine_token(sign_token(HID, 1))
    with pytest.raises(TokenError):
        verify_token(sign_refine_token(HID, "swap_shoes"))


def test_refine_expiry_and_tampering():
    t0 = 1_700_000_000.0
    token = sign_refine_token(HID, "warmer", _now=t0)
    assert verify_refine_token(token, _now=t0 + 86400) == (HID, "warmer")
    with pytest.raises(TokenError, match="expired"):
        verify_refine_token(token, _now=t0 + (DEFAULT_TTL_DAYS + 1) * 86400)
    payload, _ = token.split(".")
    _, other_sig = sign_refine_token(HID, "cooler", _now=t0).split(".")
    with pytest.raises(TokenError, match="signature"):
        verify_refine_token(f"{payload}.{other_sig}")
