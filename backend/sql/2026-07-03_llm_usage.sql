-- Issue #114: production LLM usage ledger.
-- One row per Anthropic API call, written best-effort by
-- services/claude.py::create_tracked. Stores tokens + model only, never
-- dollars — cost is derived at read time from a price map so history stays
-- truthful when prices change. Cache columns matter: input_tokens EXCLUDES
-- cached tokens, and cache reads/writes are priced differently, so cost
-- derived from input/output alone would be wrong for every cached call.
--
-- No user_id yet; it gets added with the multi-user migration like every
-- other table.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

create table if not exists llm_usage (
  id                          uuid primary key default gen_random_uuid(),
  created_at                  timestamptz not null default now(),
  call_type                   text not null,
  model                       text not null,
  input_tokens                integer not null default 0,
  output_tokens               integer not null default 0,
  cache_creation_input_tokens integer not null default 0,
  cache_read_input_tokens     integer not null default 0
);

create index if not exists llm_usage_created_at_idx
  on llm_usage (created_at desc);
