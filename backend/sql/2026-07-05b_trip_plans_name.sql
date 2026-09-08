-- Issue #134: editable trip name so Past Trips tiles stay distinguishable
-- when two saves share a destination/dates (e.g. regenerate-and-resave).
-- Nullable and additive — existing rows get NULL, which the API/UI treat as
-- "no custom name yet" and fall back to the destination display.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.
--
-- ORDERING: depends on 2026-07-05a_trip_plans.sql, which creates the table.
-- Both landed the same day; this file used to sort BEFORE the create, so a
-- fresh "run every file in date order" setup altered a table that didn't
-- exist yet. The a/b suffix makes the order unambiguous under any collation
-- (plain `_` vs `.` only works under ASCII sort, not macOS `ls`) (#161 review).

alter table trip_plans add column if not exists name text;
