"""Manual Weave trace run (#85) — NOT scheduled.

Run by hand to see the daily recommender's decision as a Weave call tree:

    uv --project backend run python jobs/trace_daily.py

Running THIS file is the opt-in to tracing. The scheduled cron runs
daily_outfit.py, which never touches weave, so automated runs stay untraced
(observability off the hot path, #85 guardrail).

We call recommend(persist=False) directly rather than daily_outfit.main(), so
this run sends no email and writes no outfit_history row — probing the pipeline
never pollutes the 👍/👎 dataset Phase 2 learns from.
"""

import logging
import sys
from pathlib import Path

# Make `services`, `observability`, `daily_outfit`, etc. importable.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

# Init tracing BEFORE importing the pipeline, so the Anthropic autopatch is in
# place before services.claude builds its client.
from observability import init_weave  # noqa: E402

init_weave()

from daily_outfit import DAILY_MODES  # noqa: E402
from services.recommend import recommend  # noqa: E402


def main() -> int:
    result = recommend(travel_mode=False, modes=DAILY_MODES, persist=False)
    print(
        f"[trace] computed {len(result['outfits'])} outfits "
        "(persist=False — no email, no DB write)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
