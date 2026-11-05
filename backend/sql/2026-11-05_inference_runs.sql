-- Issue #149: a tiny log of weekly preference-inference runs.
--
-- The heartbeat (profile.preferences_reviewed_at, #63 design) catches a DEAD
-- job — a run that never happened or crashed leaves it stale. It cannot catch
-- an ALIVE-AND-WIPED one: on 2026-07-06 the job ran cleanly, the model found no
-- pattern it could keep, and upsert_node re-derived the inferred set to empty
-- ("wrote 0, removed 2 prior"). That is correct #62 semantics, but the only
-- trace was a log.warning inside a green Actions run, and the Profile UI showed
-- a bare "No patterns learned yet" with no hint that two had just been retired.
--
-- One row per completed run (any healthy outcome — wrote prefs, found none, or
-- short-circuited on insufficient evidence). A failed run writes nothing here,
-- same as it leaves the heartbeat stale. The Profile UI reads only the newest
-- row for its empty-state copy ("No patterns this week — 2 retired Jul 6");
-- the history is kept because it is cheap and the Insights dashboard (#146)
-- will want the trend. Preferred over two counters on `profile` for exactly
-- that reason.
--
-- No user_id yet; it gets added with the multi-user migration like every
-- other table.
--
-- Run in the Supabase SQL editor before deploying the matching code. Safe to
-- re-run.

create table if not exists inference_runs (
  id        uuid primary key default gen_random_uuid(),
  ran_at    timestamptz not null default now(),
  -- 'inferred'     — wrote >= 1 statement (the normal healthy case)
  -- 'empty'        — enough evidence, model/validation kept nothing; the
  --                  prior set was removed (this is the #149 case when
  --                  removed > 0)
  -- 'insufficient' — below MIN_VERDICTS; graph short-circuited, table
  --                  untouched
  outcome   text not null check (outcome in ('inferred', 'empty', 'insufficient')),
  verdicts  integer not null default 0,  -- verdict rows the run saw
  written   integer not null default 0,  -- inferred rows inserted
  removed   integer not null default 0   -- prior active inferred rows deleted
);

create index if not exists inference_runs_ran_at_idx
  on inference_runs (ran_at desc);

-- RLS on, no policies: service_role bypasses, anon is denied (see AGENTS.md
-- "Supabase" and #161/#163 — tests/test_sql_rls.py enforces this line).
alter table public.inference_runs enable row level security;
