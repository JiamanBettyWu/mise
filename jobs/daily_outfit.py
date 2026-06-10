"""Daily outfit email — runs once a day from a GitHub Actions cron.

The cron is nominally 7am America/New_York, but GitHub's scheduled runs are
best-effort and routinely delayed 1-3h, so the email actually lands mid-morning.
We send unconditionally whenever the job runs; one cron line means one run means
one email. `TZ` is only used to label the email with the local date.
"""

import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# Make `services`, `db`, etc. importable when run as `python jobs/daily_outfit.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services.email import send_html_email  # noqa: E402
from services.email_template import render_outfit_email  # noqa: E402
from services.feedback_token import sign_token  # noqa: E402
from services.recommend import recommend  # noqa: E402

TZ = ZoneInfo("America/New_York")

DAILY_MODES = [
    {
        "name": "Smart casual",
        "description": (
            "Default mode for a normal day. Polished but relaxed — workable in "
            "an office without a strict dress code, and equally good for going "
            "out afterward. Avoid athleisure or formal-only pieces."
        ),
    },
    {
        "name": "Athleisure",
        "description": (
            "Workout-friendly, casual, comfortable for active days. Think "
            "joggers, leggings, sneakers, breathable layers. Skip dress shirts, "
            "blazers, heels, or anything restrictive."
        ),
    },
    {
        "name": "Elevated",
        "description": (
            "Polished and elegant for nicer occasions — date night, dinner, "
            "events. Lean into formal or smart-casual pieces, refined fabrics, "
            "and dressier shoes. Avoid athleisure or rugged casual."
        ),
    },
]


def main() -> int:
    now = datetime.now(TZ)
    print(f"[run] generating outfit for {now.isoformat()}")
    result = recommend(travel_mode=False, notes="", modes=DAILY_MODES)
    weather = result["weather"]
    outfits = result["outfits"]
    _attach_feedback_links(outfits)

    html = render_outfit_email(
        weather=weather,
        outfits=outfits,
        date_label=now.strftime("%A, %B %-d"),
    )

    send_html_email(
        to=os.environ["EMAIL_RECIPIENT"],
        subject=f"Today's outfit · {now.strftime('%a %b %-d')}",
        html=html,
    )
    print(f"[done] sent {len(outfits)} outfits to {os.environ['EMAIL_RECIPIENT']}")
    return 0


def _attach_feedback_links(outfits: list[dict]) -> None:
    """Add 👍/👎 URLs to each logged outfit (issue #39).

    Tokens are signed HERE, in-process on the Actions runner; the Render
    backend only verifies — so FEEDBACK_SECRET must match in both places
    (plus the local .env). Best-effort: a missing secret or URL skips the
    links but never blocks the email.
    """
    base_url = os.environ.get("BACKEND_PUBLIC_URL", "").rstrip("/")
    if not base_url or not os.environ.get("FEEDBACK_SECRET"):
        print("[warn] BACKEND_PUBLIC_URL/FEEDBACK_SECRET not set; no feedback links")
        return
    for outfit in outfits:
        history_id = outfit.get("history_id")
        if not history_id:
            continue
        outfit["feedback_urls"] = {
            "up": f"{base_url}/feedback/{sign_token(history_id, 1)}",
            "down": f"{base_url}/feedback/{sign_token(history_id, -1)}",
        }


if __name__ == "__main__":
    sys.exit(main())
