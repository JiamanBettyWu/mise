# Deploy & first-time setup checklist

This doc walks through standing the app up from scratch. It originated as the
Phase-1 skeleton guide; the database schema has grown since — see the note at
the end of step 1.

**Last checked against the repo:** 2026-10-15 ([#167](https://github.com/JiamanBettyWu/mise/issues/167)).
The commands, env-var names and file paths below were verified against the
code. The Render/Vercel/Supabase dashboard click-paths were *not* re-walked —
vendor UIs move, so treat those labels as approximate.

## 1. Supabase — create the table and storage bucket

In Supabase dashboard → SQL Editor → run:

```sql
-- Clothing items table
create table if not exists public.clothing_items (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  type text not null,
  color text not null,
  formality text not null check (formality in ('casual', 'smart-casual', 'formal')),
  season text not null check (season in ('spring', 'summer', 'fall', 'winter', 'all-season')),
  fabric text not null,
  photo_url text not null,
  available boolean not null default true,
  in_travel_bag boolean not null default false,
  notes text,
  created_at timestamptz not null default now()
);

-- Enable RLS with no policies. Our backend uses the service_role key, which
-- bypasses RLS — so the app keeps working. But the anon key (which Supabase
-- exposes by default) gets blocked from reading or writing.
-- Auth for the actual app is enforced by APP_PASSWORD in the FastAPI layer.
alter table public.clothing_items enable row level security;
```

Then in **Storage** → Create bucket:

- Name: `clothes-photos`
- **Public bucket**: ON (so we can embed photo URLs in emails without signed URLs)

If you toggled **Public bucket: ON**, you're done — Supabase creates the
public-read policy for you. Skip the SQL below.

Only run this if the bucket isn't public for some reason:

```sql
drop policy if exists "Public read clothes-photos" on storage.objects;
create policy "Public read clothes-photos"
on storage.objects for select
using ( bucket_id = 'clothes-photos' );
```

> **The schema above is the original Phase-1 table.** The live schema has since
> grown several columns (warmth, feedback attribution, etc.) plus the
> `outfit_history`, `profile`, `preferences`, `llm_usage` and `trip_plans`
> tables. After creating the base
> table, run every file in [`backend/sql/`](../backend/sql/) in date order in the
> SQL Editor — each is dated and idempotent. That directory is the source of
> truth for the current schema.
>
> **Any new table needs its own `alter table public.<t> enable row level
> security;`** — RLS is per-table and does not propagate to tables created
> later. See [`backend/sql/2026-09-08_enable_rls.sql`](../backend/sql/2026-09-08_enable_rls.sql),
> which backfilled five tables that shipped without it (#161). `tests/test_sql_rls.py`
> fails CI if a new migration forgets the line.
>
> Two migrations landing the same day carry an `a`/`b` suffix
> (`2026-07-05a_…`, `2026-07-05b_…`) when one depends on the other — plain
> filename sort is locale-dependent and got this wrong once.

## 2. Grab your Supabase keys

Project Settings → API:

- **Project URL** → `SUPABASE_URL`
- **service_role secret** → `SUPABASE_SERVICE_ROLE_KEY`  
  ⚠️ Server-side only. Never put in frontend code or commit to git.

## 3. Push the repo to GitHub

```bash
cd ~/dev/mise
git init
git add .
git commit -m "initial scaffold"
git branch -M main
git remote add origin git@github.com:<your-username>/mise.git
git push -u origin main
```

## 4. Deploy backend to Render

The live service is **dashboard-managed, not Blueprint-managed**: Render does
*not* read [`render.yaml`](../render.yaml). That file is documentation of the
settings below — copy values *from* it, and keep it in step when you change
the dashboard (see AGENTS.md → Deploy surface).

1. Render dashboard → **New** → **Web Service** → connect the repo.
2. Settings, matching `render.yaml`:
   - **Root Directory**: `backend`
   - **Runtime**: Python, **plan**: free
   - **Build Command**: `uv sync --frozen --no-dev && uv cache prune --ci`
   - **Start Command**: `uv run --no-sync uvicorn main:app --host 0.0.0.0 --port $PORT`
     (`--no-sync` is required — a bare `uv run` re-installs the dev group on boot)
   - Env var `UV_VERSION` = the value in `render.yaml` (pins uv itself).
     The Python interpreter is pinned by `backend/.python-version`, **not** by
     Render's `PYTHON_VERSION` env var — uv doesn't read that one.
   (There is no Render cron — the recurring jobs run on GitHub Actions; see step 8.)
3. In the web service env vars, paste:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `ANTHROPIC_API_KEY`
   - `APP_PASSWORD` (your chosen password)
   - `ALLOWED_ORIGINS` — for now: `http://localhost:5173` (we'll add the Vercel URL after step 5)
4. Other vars (`OPENWEATHERMAP_API_KEY` + `WEATHER_LAT`/`WEATHER_LON`,
   `SERPAPI_API_KEY`, `FEEDBACK_SECRET`) can be filled in as you enable those
   features — the backend boots without them (each one is read when its
   feature runs, not at startup). Without `SERPAPI_API_KEY`, trip plans still
   render but every purchase suggestion comes back empty.
   **Don't** put the Gmail vars (`GMAIL_SENDER`, `GMAIL_APP_PASSWORD`,
   `EMAIL_RECIPIENT`) on Render: nothing there sends mail. Only the daily job
   does, on GitHub Actions (step 8).
   `FEEDBACK_SECRET` must match the value in GitHub Actions (see step 8).
5. Note the service URL once the first deploy finishes: `https://<service-name>.onrender.com`.
6. Test: `curl https://<your-render-url>/health` → should return `{"ok": true, "supabase": true, ...}`.

## 5. Deploy frontend to Vercel

1. Vercel → **Add New** → **Project** → import the `mise` repo.
2. Set **Root Directory** = `frontend/`.
3. Framework preset: Vite (auto-detected).
4. Env vars:
   - `VITE_API_BASE_URL` = your Render URL from step 4.
5. Deploy. Note the Vercel URL.

## 6. Update CORS

Back in Render → web service env vars, set:
```
ALLOWED_ORIGINS=http://localhost:5173,https://<your-vercel-url>
```
Render will auto-redeploy.

## 7. End-to-end test

- Visit your Vercel URL.
- Enter `APP_PASSWORD` → the password gate should give way to the app (nav:
  Catalog · Today · Trip · Add). The gate checks it against `GET /health/auth`.
- Wrong password should show "Wrong password." "Could not reach the server"
  means the frontend can't reach the backend — usually `VITE_API_BASE_URL` or
  CORS (step 6).

## 8. Daily email + weekly inference (GitHub Actions)

The recurring jobs run on **GitHub Actions**, not Render Cron (Render Cron needs
a paid plan): the daily email, the weekly preference inference, and a nightly
orphaned-photo sweep. Add the Actions secrets and test the workflows following
[docs/daily-email.md](daily-email.md).

## Render free-tier note
Free web services spin down when idle and take a while (tens of seconds) to wake
on the first request — Render's exact numbers change, so check their docs. That's fine for a personal app — and it doesn't affect the daily email,
which runs on GitHub Actions, not Render.
