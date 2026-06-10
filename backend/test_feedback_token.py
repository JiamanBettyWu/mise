"""Tests for the signed feedback tokens (issue #39).

Run from repo root:  python backend/test_feedback_token.py

Pure-Python, no network. FEEDBACK_SECRET is set in-process; expiry is tested
via the _now injection point rather than sleeping.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

os.environ["FEEDBACK_SECRET"] = "test-secret-do-not-use"

from services.feedback_token import (  # noqa: E402
    DEFAULT_TTL_DAYS,
    TokenError,
    sign_token,
    verify_token,
)

HID = "1f4a2b3c-0000-4000-8000-123456789abc"


def must_fail(token, _now=None):
    try:
        verify_token(token, _now=_now)
    except TokenError as e:
        return str(e)
    raise AssertionError(f"token unexpectedly verified: {token!r}")


# --- 1. round trip ---------------------------------------------------------------
assert verify_token(sign_token(HID, 1)) == (HID, 1)
assert verify_token(sign_token(HID, -1)) == (HID, -1)
print("✓ round trip: up and down verdicts survive sign→verify")


# --- 2. tokens are URL-safe ------------------------------------------------------
token = sign_token(HID, 1)
assert all(c.isalnum() or c in "-_." for c in token), token
print("✓ tokens contain only URL-safe characters (no escaping needed in links)")


# --- 3. tampering is rejected ----------------------------------------------------
up, down = sign_token(HID, 1, _now=1000.0), sign_token(HID, -1, _now=1000.0)
payload, sig = up.split(".")
other_payload, _ = down.split(".")
assert "signature" in must_fail(f"{other_payload}.{sig}")  # payload swap
flipped = payload[:-1] + ("A" if payload[-1] != "A" else "B")
assert must_fail(f"{flipped}.{sig}")  # single-char payload flip
assert "malformed" in must_fail("not-a-token")
assert "malformed" in must_fail("")
assert "malformed" in must_fail("a.b.c.d")
print("✓ tampered payloads, swapped signatures, and garbage all rejected")


# --- 4. expiry -------------------------------------------------------------------
t0 = 1_700_000_000.0
token = sign_token(HID, 1, _now=t0)
assert verify_token(token, _now=t0 + (DEFAULT_TTL_DAYS - 1) * 86400) == (HID, 1)
assert "expired" in must_fail(token, _now=t0 + (DEFAULT_TTL_DAYS + 1) * 86400)
print(f"✓ expiry: valid at day {DEFAULT_TTL_DAYS - 1}, rejected after day {DEFAULT_TTL_DAYS}")


# --- 5. wrong secret -------------------------------------------------------------
token = sign_token(HID, 1)
os.environ["FEEDBACK_SECRET"] = "a-different-secret"
assert "signature" in must_fail(token)
os.environ["FEEDBACK_SECRET"] = ""
assert "not configured" in must_fail(token)
os.environ["FEEDBACK_SECRET"] = "test-secret-do-not-use"
assert verify_token(token) == (HID, 1)  # restored secret works again
print("✓ secret mismatch and missing FEEDBACK_SECRET both rejected")


# --- 6. invalid verdicts can't be signed -----------------------------------------
try:
    sign_token(HID, 0)
    raise AssertionError("verdict 0 unexpectedly accepted")
except ValueError:
    pass
print("✓ sign_token rejects verdicts other than +1/-1")


print("\nAll feedback-token tests passed.")
