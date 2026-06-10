"""GET /feedback/{token} — records a thumbs verdict from a daily-email link.

Deliberately OUTSIDE require_password: the link is clicked from an email
client that can't send headers, so the HMAC-signed token IS the auth (see
services/feedback_token.py). Idempotent — re-clicking, or clicking the other
thumb, overwrites the verdict so you can change your mind.

A GET that mutates state is technically impure; acceptable for a Gmail-only
recipient (Gmail proxies images but doesn't auto-click links). Escape hatch
if that ever changes: turn this into a confirm-button landing page.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from postgrest.exceptions import APIError

from db.supabase import client as supabase
from services.feedback_token import TokenError, verify_token

log = logging.getLogger("wardrobe.feedback")

router = APIRouter(prefix="/feedback", tags=["feedback"])

VERDICT_LABELS = {1: "👍 Thumbs up", -1: "👎 Thumbs down"}


@router.get("/{token}", response_class=HTMLResponse)
def record_feedback(token: str) -> HTMLResponse:
    try:
        history_id, verdict = verify_token(token)
    except TokenError as e:
        log.warning("feedback token rejected: %s", e)
        return _page(
            "Link not valid",
            "This feedback link is invalid or has expired (links last 14 days).",
            status_code=400,
        )

    try:
        res = (
            supabase()
            .table("outfit_history")
            .update(
                {
                    "feedback": verdict,
                    "feedback_at": datetime.now(timezone.utc).isoformat(),
                }
            )
            .eq("id", history_id)
            .execute()
        )
    except APIError:
        log.error("feedback update failed for history_id=%s", history_id, exc_info=True)
        return _page(
            "Something went wrong",
            "Couldn't save your feedback — try the link again in a minute.",
            status_code=500,
        )
    if not res.data:
        return _page(
            "Outfit not found",
            "This outfit is no longer in the history.",
            status_code=404,
        )

    row = res.data[0]
    return _page(
        f"{VERDICT_LABELS[verdict]} recorded",
        f"For the <strong>{row['mode']}</strong> outfit of {row['recommended_on']}. "
        "Changed your mind? Click the other thumb in the email — the latest "
        "click wins.",
    )


def _page(title: str, detail: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font-family:-apple-system,system-ui,sans-serif;max-width:480px;
             margin:15vh auto 0;padding:0 16px;color:#222;text-align:center;">
  <h1 style="font-size:22px;">{title}</h1>
  <p style="color:#555;font-size:15px;line-height:1.5;">{detail}</p>
  <p style="color:#aaa;font-size:13px;margin-top:32px;">Wardrobe AI</p>
</body></html>
""",
        status_code=status_code,
    )
