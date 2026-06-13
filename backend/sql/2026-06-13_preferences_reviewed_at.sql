-- Issue #62 follow-up: a "last reviewed" heartbeat for the weekly inference job.
--
-- The job stamps profile.preferences_reviewed_at = now() as the last action of
-- a successful run (any healthy outcome — wrote prefs, found none, or short-
-- circuited on insufficient evidence). A failed run raises before the stamp, so
-- the value goes stale. The Profile UI surfaces it as relative time ("9 days
-- ago"); staleness is the alarm, which catches every failure mode — including a
-- GitHub-disabled cron that never fires and so can never log its own failure.
--
-- Run in the Supabase SQL editor before deploying the matching code. Safe to re-run.

alter table profile
  add column if not exists preferences_reviewed_at timestamptz;
