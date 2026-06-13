"""Weekly preference-inference job (#62) — runs from a GitHub Actions cron.

Reads the full outfit-verdict history and distills durable style preferences
into the `preferences` table as source = 'inferred' (re-derived from scratch
each run). The whole pipeline is a LangGraph in
backend/services/preference_inference.py; this file is just the entry point —
env loading, logging, and turning the graph's outcome into an exit code.

Unlike jobs/daily_outfit.py, a failed run here costs nothing: it leaves the
inferred set exactly as it was and exits nonzero. The graph never deletes
before it has successfully inserted, so a crash can't wipe the user's prefs.
"""

import logging
import sys
from pathlib import Path

# Make `services`, `db`, etc. importable when run as `python jobs/infer_preferences.py`.
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))

# Surface the graph's INFO diagnostics (verdict count, drops, re-derive counts)
# in the Actions log — "why did nothing get written this week?" must have an
# exact answer there.
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd (same contract as the other
# two entry points — see AGENTS.md, "Single .env at repo root").
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from services.preference_inference import MIN_VERDICTS, run  # noqa: E402


def main() -> int:
    print("[run] inferring preferences from outfit-verdict history")
    summary = run()

    written = summary.get("written")
    if written is None:
        # Graph short-circuited at the evidence gate; nothing was touched.
        print(
            f"[done] insufficient evidence ({summary['verdicts']} verdicts "
            f"< {MIN_VERDICTS}); inferred preferences left untouched"
        )
        return 0

    for pref in summary.get("inferred", []):
        print(f"[pref] {pref['text']}  (from {len(pref['evidence_ids'])} outfits)")
    print(
        f"[done] re-derived inferred preferences from {summary['verdicts']} "
        f"verdicts: wrote {written}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
