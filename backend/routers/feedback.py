"""GET /feedback/{token} — records a thumbs verdict from a daily-email link.

Deliberately OUTSIDE require_password: the link is clicked from an email
client that can't send headers, so the HMAC-signed token IS the auth (see
services/feedback_token.py). Idempotent — re-clicking, or clicking the other
thumb, overwrites the verdict so you can change your mind.

A GET that mutates state is technically impure; acceptable for a Gmail-only
recipient (Gmail proxies images but doesn't auto-click links). Escape hatch
if that ever changes: turn this into a confirm-button landing page.

The 👎 landing page doubles as the optional attribution follow-up (#60):
chips for the outfit's items / the combo / the weather call / the occasion,
plus free text, submitting to POST /feedback/{token}/attribution. The same
token is reused as auth — blast radius unchanged (one row).
"""

import html
import logging
from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse
from postgrest.exceptions import APIError
from pydantic import BaseModel

from db.supabase import client as supabase
from services.feedback_token import TokenError, verify_token
from services.outfit_history import AttributionError, record_attribution

log = logging.getLogger("wardrobe.feedback")

router = APIRouter(prefix="/feedback", tags=["feedback"])

VERDICT_LABELS = {1: "👍 Thumbs up", -1: "👎 Thumbs down"}


class AttributionBody(BaseModel):
    reason: Literal["specific_items", "combination", "weather", "occasion"] | None = (
        None
    )
    item_ids: list[str] = []
    note: str = ""


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
            .select("mode, recommended_on, feedback, item_ids")
            .eq("id", history_id)
            .execute()
        )
        if not res.data:
            return _page(
                "Outfit not found",
                "This outfit is no longer in the history.",
                status_code=404,
            )
        row = res.data[0]

        update = {
            "feedback": verdict,
            "feedback_at": datetime.now(timezone.utc).isoformat(),
        }
        # Attribution belongs to the verdict act it followed (#60): a flip
        # wipes it, but re-clicking the same thumb must not destroy a
        # follow-up already submitted from this very page.
        if row.get("feedback") != verdict:
            update |= {
                "feedback_reason": None,
                "feedback_item_ids": None,
                "feedback_note": None,
            }
        supabase().table("outfit_history").update(update).eq("id", history_id).execute()
    except APIError:
        log.error("feedback update failed for history_id=%s", history_id, exc_info=True)
        return _page(
            "Something went wrong",
            "Couldn't save your feedback — try the link again in a minute.",
            status_code=500,
        )

    extra = _attribution_form(token, row.get("item_ids") or []) if verdict == -1 else ""
    return _page(
        f"{VERDICT_LABELS[verdict]} recorded",
        f"For the <strong>{row['mode']}</strong> outfit of {row['recommended_on']}. "
        "Changed your mind? Click the other thumb in the email — the latest "
        "click wins.",
        extra_html=extra,
    )


@router.post("/{token}/attribution")
def record_feedback_attribution(token: str, body: AttributionBody):
    """Optional 👎 follow-up from the email landing page (#60).

    Token-authed twin of POST /outfits/{history_id}/attribution — the page
    is opened from an email, so the HMAC token is the only credential the
    browser has. Only 👎 tokens qualify; the row guard inside
    record_attribution additionally rejects rows whose verdict has since
    changed (latest write wins across channels).
    """
    try:
        history_id, verdict = verify_token(token)
    except TokenError as e:
        raise HTTPException(status_code=400, detail=str(e))
    if verdict != -1:
        raise HTTPException(
            status_code=400, detail="attribution follows a 👎 link only"
        )
    try:
        record_attribution(history_id, body.reason, body.item_ids, body.note)
    except AttributionError as e:
        raise HTTPException(status_code=e.status, detail=str(e))
    return {"history_id": history_id, "recorded": True}


def _attribution_form(token: str, item_ids: list[str]) -> str:
    """The optional what-was-off chips for the 👎 landing page.

    Item chips imply reason 'specific_items' and are exclusive with the
    three outfit-level reason chips; one reason at most. Submitting is
    optional — the verdict is already recorded by the time this renders.
    Plain inline HTML/JS like the rest of the page; the token is URL-safe
    base64 so it interpolates into the fetch path directly.
    """
    names = {}
    if item_ids:
        res = (
            supabase()
            .table("clothing_items")
            .select("id, name")
            .in_("id", item_ids)
            .execute()
        )
        names = {r["id"]: r["name"] for r in (res.data or [])}

    item_chips = "".join(
        f'<button type="button" class="chip" data-item="{iid}">'
        f"{html.escape(names[iid])}</button>"
        for iid in item_ids
        if iid in names
    )
    return f"""
<style>
  .chips {{ display:flex; flex-wrap:wrap; gap:8px; justify-content:center; margin:10px 0; }}
  .chip {{ border:1px solid #ccc; background:#fff; border-radius:999px;
           padding:6px 14px; font-size:14px; cursor:pointer; color:#444; }}
  .chip.on {{ background:#222; border-color:#222; color:#fff; }}
  #attr input {{ width:100%; box-sizing:border-box; margin:6px 0 12px; padding:8px 12px;
                 border:1px solid #ccc; border-radius:12px; font-size:14px; }}
  #attr [type=submit] {{ border:1px solid #222; background:#222; color:#fff;
                         border-radius:999px; padding:8px 20px; font-size:14px; cursor:pointer; }}
</style>
<form id="attr" style="margin-top:28px;border-top:1px solid #eee;padding-top:20px;">
  <p style="color:#555;font-size:15px;">Optional — what was off?</p>
  <div class="chips">{item_chips}</div>
  <div class="chips">
    <button type="button" class="chip" data-reason="combination">The combination</button>
    <button type="button" class="chip" data-reason="weather">The weather call</button>
    <button type="button" class="chip" data-reason="occasion">Wrong for the occasion</button>
  </div>
  <input id="note" placeholder="Anything else? (optional)">
  <button type="submit">Send</button>
  <p id="attr-err" style="color:#b3261e;font-size:13px;"></p>
</form>
<script>
(function () {{
  var form = document.getElementById("attr");
  var all = function (sel) {{ return Array.prototype.slice.call(form.querySelectorAll(sel)); }};
  var itemChips = all("[data-item]"), reasonChips = all("[data-reason]");
  itemChips.forEach(function (c) {{
    c.onclick = function () {{
      c.classList.toggle("on");
      reasonChips.forEach(function (r) {{ r.classList.remove("on"); }});
    }};
  }});
  reasonChips.forEach(function (c) {{
    c.onclick = function () {{
      var was = c.classList.contains("on");
      reasonChips.forEach(function (r) {{ r.classList.remove("on"); }});
      itemChips.forEach(function (i) {{ i.classList.remove("on"); }});
      if (!was) c.classList.add("on");
    }};
  }});
  form.onsubmit = function (ev) {{
    ev.preventDefault();
    var on = function (c) {{ return c.classList.contains("on"); }};
    var items = itemChips.filter(on).map(function (c) {{ return c.getAttribute("data-item"); }});
    var picked = reasonChips.filter(on)[0];
    var reason = items.length ? "specific_items" : (picked ? picked.getAttribute("data-reason") : null);
    var note = document.getElementById("note").value.trim();
    if (!reason && !note) return;
    fetch("/feedback/{token}/attribution", {{
      method: "POST",
      headers: {{ "Content-Type": "application/json" }},
      body: JSON.stringify({{ reason: reason, item_ids: items, note: note }}),
    }}).then(function (r) {{
      if (!r.ok) throw new Error();
      form.outerHTML = '<p style="color:#555;font-size:15px;margin-top:28px;">Noted — thank you.</p>';
    }}).catch(function () {{
      document.getElementById("attr-err").textContent = "Couldn't save — try again.";
    }});
  }};
}})();
</script>
"""


def _page(
    title: str, detail: str, status_code: int = 200, extra_html: str = ""
) -> HTMLResponse:
    return HTMLResponse(
        f"""<!doctype html>
<html><head><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title></head>
<body style="font-family:-apple-system,system-ui,sans-serif;max-width:480px;
             margin:15vh auto 0;padding:0 16px;color:#222;text-align:center;">
  <h1 style="font-size:22px;">{title}</h1>
  <p style="color:#555;font-size:15px;line-height:1.5;">{detail}</p>
  {extra_html}
  <p style="color:#aaa;font-size:13px;margin-top:32px;">Wardrobe AI</p>
</body></html>
""",
        status_code=status_code,
    )
