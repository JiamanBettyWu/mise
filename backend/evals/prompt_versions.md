# Outfit-prompt version registry (#143)

Reverse lookup for the `prompt_sha` stamped into `outfit_history.config`:
`sha256(OUTFIT_SYSTEM_PROMPT)[:8]` at the time the row was written. The
fingerprint is computed from the prompt text itself, so any prompt edit mints
a new sha automatically — and `backend/tests/test_config_fingerprint.py`
fails CI until the new sha is added here. Registered by compulsion, not
memory: append a row, never edit or delete old ones.

Rows with `config IS NULL` predate versioning (before 2026-07-09).

| prompt_sha | date registered | PR | description |
|------------|-----------------|----|-------------|
| `5e98927e` | 2026-07-09 | #143 (initial registry) | Prompt as of #135: recent-picks variety block, candidates shape, warmth/gate rules. |
