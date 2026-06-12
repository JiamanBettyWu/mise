-- Issue #60: optional 👎 attribution + recommendation-time context.
--
-- Attribution converts a smeared outfit-level 👎 into a precise signal:
--   feedback_reason   what the thumbs-down was really about
--   feedback_item_ids the named culprits, only when reason = 'specific_items'
--   feedback_note     optional free text
-- Flipping or clearing the verdict wipes all three (latest write wins).
--
-- weather + notes are captured at recommendation time in log_outfits():
-- the weekly preference-inference job (#62) needs "what was the weather /
-- the ask when she judged this", and neither can be backfilled later.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

alter table outfit_history
  add column if not exists feedback_reason text
    check (feedback_reason in ('specific_items', 'combination', 'weather', 'occasion')),
  add column if not exists feedback_item_ids uuid[],
  add column if not exists feedback_note text,
  add column if not exists weather jsonb,
  add column if not exists notes text;
