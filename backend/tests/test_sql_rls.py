"""RLS guardrail for the SQL migrations (#163).

Enforcement half of the #161 fix. RLS is *per-table* and does not propagate to
tables created later, and nothing fails loudly when a migration omits it — that
is exactly how five tables shipped without RLS and went unnoticed for three
months until Supabase's Security Advisor emailed about it.

Same posture as test_config_fingerprint.py: the convention is stated in
AGENTS.md, and this test is what makes it true by compulsion rather than by
memory. It asserts across the whole directory, not per-file, so the backfill
migration legitimately covers the older files; a table added tomorrow has no
such backfill and fails.
"""

import re
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parents[1] / "sql"

# Tables created outside backend/sql/ that still carry RLS. clothing_items is
# created by the setup SQL in docs/deploy.md step 1, which enables RLS inline.
EXTERNALLY_CREATED = {"clothing_items"}

_COMMENT = re.compile(r"--[^\n]*")
_CREATE = re.compile(
    r"\bcreate\s+table\s+(?:if\s+not\s+exists\s+)?([\w.]+)", re.IGNORECASE
)
_ENABLE_RLS = re.compile(
    r"\balter\s+table\s+(?:if\s+exists\s+)?([\w.]+)\s+enable\s+row\s+level\s+security",
    re.IGNORECASE,
)


def _statements() -> str:
    """All migration SQL, comments stripped so prose can't match a pattern."""
    return "\n".join(
        _COMMENT.sub("", f.read_text()) for f in sorted(SQL_DIR.glob("*.sql"))
    )


def _bare(name: str) -> str:
    """Normalize `public.foo` and `foo` to the same key."""
    return name.split(".")[-1].lower()


def test_every_created_table_enables_rls():
    sql = _statements()
    created = {_bare(m) for m in _CREATE.findall(sql)}
    secured = {_bare(m) for m in _ENABLE_RLS.findall(sql)}

    assert created, "found no `create table` in backend/sql/ — parser is broken"

    missing = sorted(created - secured)
    assert not missing, (
        "these tables are created in backend/sql/ but never get RLS enabled: "
        f"{', '.join(missing)}. Add `alter table public.<t> enable row level "
        "security;` to the migration that creates each one — RLS is per-table "
        "and does not propagate. See AGENTS.md ('Supabase') and #161."
    )


def test_rls_statements_name_real_tables():
    """A typo'd table name would pass the check above while securing nothing."""
    sql = _statements()
    created = {_bare(m) for m in _CREATE.findall(sql)}
    secured = {_bare(m) for m in _ENABLE_RLS.findall(sql)}

    unknown = sorted(secured - created - EXTERNALLY_CREATED)
    assert not unknown, (
        f"RLS is enabled on tables that no migration creates: {', '.join(unknown)}. "
        "Either a typo (the statement would error in the SQL Editor and secure "
        "nothing), or a table created outside backend/sql/ — if the latter, add "
        "it to EXTERNALLY_CREATED with a comment saying where it comes from."
    )
