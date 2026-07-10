-- Issue #143: prompt/config cohort label on outfit_history.
-- `config` records which prompt + sampler configuration generated the row:
--   {prompt_sha, daily_decay, sample_fraction, small_category_max, model}
-- written by services/outfit_history.py::log_outfits from
-- services/recommend.py::RECOMMEND_CONFIG (prompt_sha = first 8 hex chars of
-- sha256(OUTFIT_SYSTEM_PROMPT)). Pre-migration rows stay NULL, which reports
-- read as "pre-versioning". Reverse lookup sha -> prompt text lives in
-- backend/evals/prompt_versions.md.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

alter table outfit_history add column if not exists config jsonb;
