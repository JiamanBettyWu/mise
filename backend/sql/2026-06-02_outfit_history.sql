-- Issue #15: per-(date, mode) recommendation log.
-- Drives the recency-decay sampler in backend/services/outfit_history.py
-- so Claude stops anchoring on the top of the wardrobe list.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

create table if not exists outfit_history (
  id              uuid primary key default gen_random_uuid(),
  recommended_on  date not null,
  mode            text not null,
  item_ids        uuid[] not null,
  created_at      timestamptz not null default now()
);

create index if not exists outfit_history_recommended_on_idx
  on outfit_history (recommended_on desc);
