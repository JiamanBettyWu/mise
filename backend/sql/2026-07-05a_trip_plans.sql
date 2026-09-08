-- Issue #128: explicit trip-plan saving.
-- Frozen snapshot of a generated TripPlanResponse, saved only on deliberate
-- user action (POST /trips never happens automatically). The catalog is
-- alive — items get deleted/renamed — so `plan` stores the full blob as of
-- save time, purchase links included even though they rot.
--
-- `edited` is true when the user pruned packing-list items client-side before
-- saving; keeps saved plans usable as eval data without contaminating "what
-- the model produced" for plans nobody touched.
--
-- No user_id yet; it gets added with the multi-user migration like every
-- other table.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

create table if not exists trip_plans (
  id           uuid primary key default gen_random_uuid(),
  created_at   timestamptz not null default now(),
  destination  text not null,
  start_date   date not null,
  end_date     date not null,
  notes        text not null default '',
  plan         jsonb not null,
  edited       boolean not null default false
);

create index if not exists trip_plans_created_at_idx
  on trip_plans (created_at desc);
