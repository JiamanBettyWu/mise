"""Daily outfit email — runs from GitHub Actions cron at 11:00 + 12:00 UTC.

Only the run that lands at 7am America/New_York actually sends; the other
no-ops. This way DST is handled automatically.
"""

import os
import sys
from datetime import datetime
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


def main() -> int:
    force = FORCE_FLAG in sys.argv
    now = datetime.now(TZ)
    if not force and now.hour != TARGET_HOUR:
        print(f"[skip] local hour={now.hour} != target={TARGET_HOUR} ({TZ})")
        return 0

    print(f"[run] generating outfit for {now.isoformat()}")
    result = recommend(travel_mode=False, notes="", n=3)
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
