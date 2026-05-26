"""Daily outfit email — runs from GitHub Actions cron at 11:00 + 12:00 UTC.

Only the run that lands at 7am America/New_York actually sends; the other
no-ops. This way DST is handled automatically.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# Make `services`, `db`, etc. importable when run as `python jobs/daily_outfit.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

from dotenv import load_dotenv

load_dotenv()

from services.email import send_html_email  # noqa: E402
from services.email_template import render_outfit_email  # noqa: E402
from services.recommend import recommend  # noqa: E402

TZ = ZoneInfo("America/New_York")
TARGET_HOUR = 7
FORCE_FLAG = "--force"

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
    force = FORCE_FLAG in sys.argv
    utc_now = datetime.now(timezone.utc)
    now = datetime.now(TZ)
    print(f"[debug] utc={utc_now.isoformat()} local={now.isoformat()} target_hour={TARGET_HOUR}")
    if not force and now.hour != TARGET_HOUR:
        print(f"[skip] local hour={now.hour} != target={TARGET_HOUR} ({TZ})")
        return 0

    print(f"[run] generating outfit for {now.isoformat()}")
    result = recommend(travel_mode=False, notes="", modes=DAILY_MODES)
    weather = result["weather"]
    outfits = result["outfits"]

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


if __name__ == "__main__":
    sys.exit(main())
