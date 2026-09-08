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

_LINE_COMMENT = re.compile(r"--[^\n]*")
_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)

# The modifier slot matters: `create unlogged table foo` and `create temp table
# foo` are `create table` statements the naive pattern silently skips, and a
# skipped table is a false PASS in exactly the case this guard exists to catch.
_TABLE_MODIFIERS = r"(?:(?:global|local)\s+)?(?:temp(?:orary)?|unlogged)?\s*"
_CREATE = re.compile(
    rf"\bcreate\s+{_TABLE_MODIFIERS}table\s+(?:if\s+not\s+exists\s+)?([\w.]+)",
    re.IGNORECASE,
)
_ENABLE_RLS = re.compile(
    r"\balter\s+table\s+(?:if\s+exists\s+)?([\w.]+)\s+enable\s+row\s+level\s+security",
    re.IGNORECASE,
)


def _statements() -> str:
    """All migration SQL, normalized so the patterns above see bare identifiers.

    Both comment forms are stripped (prose must not match a pattern), and double
    quotes are dropped so a quoted identifier — `create table "audit_log"` — is
    still seen. Quoted identifiers are case-sensitive in Postgres while bare ones
    fold to lower; we lower everything in _bare(), which is right for this repo's
    all-lowercase names and would only ever over-match, never under-match.
    """
    sql = "\n".join(f.read_text() for f in sorted(SQL_DIR.glob("*.sql")))
    sql = _BLOCK_COMMENT.sub("", _LINE_COMMENT.sub("", sql))
    return sql.replace('"', "")


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
    """Catch an RLS statement that points at nothing.

    Not the typo case — `alter table fooo` leaves `foo` unsecured, so the check
    above already fails. This one catches a *stale or extra* statement: a table
    since dropped or renamed, or one created outside backend/sql/. Those error
    in the SQL Editor and secure nothing, while leaving the check above green.
    """
    sql = _statements()
    created = {_bare(m) for m in _CREATE.findall(sql)}
    secured = {_bare(m) for m in _ENABLE_RLS.findall(sql)}

    unknown = sorted(secured - created - EXTERNALLY_CREATED)
    assert not unknown, (
        f"RLS is enabled on tables that no migration creates: {', '.join(unknown)}. "
        "Either the table was dropped/renamed and this statement is stale (it "
        "would error in the SQL Editor and secure nothing), or it is created "
        "outside backend/sql/ — if the latter, add it to EXTERNALLY_CREATED "
        "with a comment saying where it comes from."
    )
