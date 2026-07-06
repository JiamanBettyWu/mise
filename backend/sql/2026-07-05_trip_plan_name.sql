-- Issue #134: editable trip name so Past Trips tiles stay distinguishable
-- when two saves share a destination/dates (e.g. regenerate-and-resave).
-- Nullable and additive — existing rows get NULL, which the API/UI treat as
-- "no custom name yet" and fall back to the destination display.
--
-- Run this in the Supabase SQL editor before deploying the matching code.
-- Safe to re-run.

alter table trip_plans add column if not exists name text;
