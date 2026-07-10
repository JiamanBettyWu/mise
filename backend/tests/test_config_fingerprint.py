"""Prompt/config versioning guardrails (#143).

The registry test is the enforcement half of the design: any edit to
OUTFIT_SYSTEM_PROMPT mints a new prompt_sha, and this test fails CI until the
sha is appended to backend/evals/prompt_versions.md — so the reverse lookup
(hash on a live outfit_history row -> which prompt text) can never silently
go stale.
"""

import hashlib
from pathlib import Path

from services.claude import MODEL, OUTFIT_SYSTEM_PROMPT
from services.recommend import RECOMMEND_CONFIG

REGISTRY = Path(__file__).resolve().parents[1] / "evals" / "prompt_versions.md"


def test_prompt_sha_is_registered():
    sha = hashlib.sha256(OUTFIT_SYSTEM_PROMPT.encode()).hexdigest()[:8]
    assert sha in REGISTRY.read_text(), (
        f"prompt_sha {sha} is not in {REGISTRY.name} — the outfit prompt "
        "changed. Append a registry row (sha, date, PR, one-line description) "
        "to backend/evals/prompt_versions.md so live rows stay attributable."
    )


def test_config_shape():
    # The cohort label must stay self-describing: exact keys, derived values.
    assert set(RECOMMEND_CONFIG) == {
        "prompt_sha",
        "daily_decay",
        "sample_fraction",
        "small_category_max",
        "model",
    }
    assert (
        RECOMMEND_CONFIG["prompt_sha"]
        == hashlib.sha256(OUTFIT_SYSTEM_PROMPT.encode()).hexdigest()[:8]
    )
    assert RECOMMEND_CONFIG["model"] == MODEL
