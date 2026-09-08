-- Enable Row-Level Security on the five tables that were created without it.
--
-- Why no policies: the backend talks to Supabase with the service_role key,
-- which has BYPASSRLS — so "RLS on, zero policies" is a deny-all wall for the
-- public anon key while the app keeps working untouched. Real auth for the app
-- is APP_PASSWORD at the FastAPI layer (backend/auth.py).
--
-- public.clothing_items already had this from the original setup SQL in
-- docs/deploy.md; these five tables were added by later migrations that
-- omitted the line, which is what Supabase's Security Advisor flagged
-- (2026-09-08). Idempotent: re-running is a no-op.

alter table public.outfit_history enable row level security;
alter table public.preferences    enable row level security;
alter table public.profile        enable row level security;
alter table public.llm_usage      enable row level security;
alter table public.trip_plans     enable row level security;
