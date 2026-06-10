"""HMAC-signed tokens for the email feedback links (issue #39).

An email link is a bare GET — no X-App-Password header, no JS — so the auth
rides in the link itself. Token shape:

    base64url(payload) "." base64url(hmac_sha256(FEEDBACK_SECRET, payload))

where payload is "<history_id>:<up|down>:<unix expiry>". Stdlib only; design
rationale in docs/feedback-loop-design.md (D1).

FEEDBACK_SECRET must be identical wherever tokens are SIGNED (the GitHub
Actions runner executing jobs/daily_outfit.py) and VERIFIED (the Render
backend serving GET /feedback/{token}); local .env holds the third copy.
"""

import base64
import binascii
import hashlib
import hmac
import os
import time

DEFAULT_TTL_DAYS = 14

_VERDICT_NAMES = {1: "up", -1: "down"}
_VERDICT_VALUES = {name: value for value, name in _VERDICT_NAMES.items()}


class TokenError(ValueError):
    """Malformed, tampered, or expired feedback token."""


def sign_token(
    history_id: str,
    verdict: int,
    ttl_days: int = DEFAULT_TTL_DAYS,
    _now: float | None = None,
) -> str:
    name = _VERDICT_NAMES.get(verdict)
    if name is None:
        raise ValueError(f"verdict must be +1 or -1, got {verdict!r}")
    now = time.time() if _now is None else _now
    expiry = int(now + ttl_days * 86400)
    payload = f"{history_id}:{name}:{expiry}".encode()
    sig = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return f"{_b64(payload)}.{_b64(sig)}"


def verify_token(token: str, _now: float | None = None) -> tuple[str, int]:
    """Return (history_id, verdict) for a valid token; raise TokenError otherwise.

    Signature is checked before anything in the payload is trusted, with
    hmac.compare_digest (constant-time)."""
    try:
        payload_b64, sig_b64 = token.split(".")
        payload = _unb64(payload_b64)
        sig = _unb64(sig_b64)
    except (ValueError, binascii.Error) as e:
        raise TokenError("malformed token") from e

    expected = hmac.new(_secret(), payload, hashlib.sha256).digest()
    if not hmac.compare_digest(sig, expected):
        raise TokenError("signature mismatch")

    parts = payload.decode().split(":")
    if len(parts) != 3 or parts[1] not in _VERDICT_VALUES:
        raise TokenError("malformed payload")
    history_id, name, expiry_str = parts

    now = time.time() if _now is None else _now
    if now > int(expiry_str):
        raise TokenError("token expired")
    return history_id, _VERDICT_VALUES[name]


def _secret() -> bytes:
    secret = os.environ.get("FEEDBACK_SECRET", "")
    if not secret:
        raise TokenError("FEEDBACK_SECRET not configured")
    return secret.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))
