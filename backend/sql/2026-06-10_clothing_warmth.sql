-- Issue #40: per-item warmth rating (1-5), the quantitative weather handle.
-- `season` is demoted to display metadata — no logic should depend on it
-- going forward (see docs/feedback-loop-design.md, D4/D5).
--
-- Run this in the Supabase SQL editor BEFORE merging the matching code:
-- `warmth` joins the wardrobe SELECT used by /outfits/today and the daily
-- email job, so deploying the code against a missing column would 400 every
-- wardrobe load. Safe to re-run.

alter table clothing_items
  add column if not exists warmth smallint
    check (warmth between 1 and 5);   -- NULL = not yet rated
