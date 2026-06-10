-- Issue #39: outfit-level thumbs up/down from the daily email.
-- Verdicts land on the existing outfit_history rows (one row per date+mode);
-- the signed-token links in the email resolve to a row id.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

alter table outfit_history
  add column if not exists feedback smallint
    check (feedback in (-1, 1)),          -- +1 = thumbs up, -1 = down, NULL = no verdict
  add column if not exists feedback_at timestamptz;
