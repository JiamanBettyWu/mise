-- Issue #61: user-provided preferences profile + home location.
--
-- preferences: short style statements (user-authored or inferred by #62).
--   source = 'user' | 'inferred'
--   status = 'active' | 'rejected'
--   Deleting a user pref is a real delete; deleting an inferred pref sets
--   status = 'rejected' so the weekly job (#62) won't resurrect it.
--   Editing an inferred pref promotes it to source = 'user' in the router.
--   evidence_ids: outfit_history rows backing an inferred pref; empty for user prefs.
--
-- profile: single-row table for home location (not a preference statement).
--   lat/lon used as the weather default in recommend(), overriding the env vars.
--
-- Run in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

create table if not exists preferences (
  id           uuid primary key default gen_random_uuid(),
  text         text not null check (char_length(text) between 1 and 500),
  source       text not null default 'user'
                 check (source in ('user', 'inferred')),
  status       text not null default 'active'
                 check (status in ('active', 'rejected')),
  evidence_ids uuid[] not null default '{}',
  created_at   timestamptz not null default now(),
  updated_at   timestamptz not null default now()
);

create table if not exists profile (
  id                  uuid primary key default gen_random_uuid(),
  home_location_text  text,
  home_lat            double precision,
  home_lon            double precision,
  updated_at          timestamptz not null default now()
);
