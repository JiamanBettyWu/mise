# Deploy & first-time setup checklist

This doc walks through standing the app up from scratch. It originated as the
Phase-1 skeleton guide; the steps below still work, but the database schema has
grown since — see the note at the end of step 1.

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
> `outfit_history`, `profile`, and `preferences` tables. After creating the base
> table, run every file in [`backend/sql/`](../backend/sql/) in date order in the
> SQL Editor — each is dated and idempotent. That directory is the source of
> truth for the current schema.

## 2. Grab your Supabase keys

Project Settings → API:

- **Project URL** → `SUPABASE_URL`
- **service_role secret** → `SUPABASE_SERVICE_ROLE_KEY`  
  ⚠️ Server-side only. Never put in frontend code or commit to git.

## 3. Push the repo to GitHub

```bash
cd ~/dev/wardrobe-ai
git init
git add .
git commit -m "initial scaffold"
git branch -M main
git remote add origin git@github.com:<your-username>/wardrobe-ai.git
git push -u origin main
```

## 4. Deploy backend to Render

1. Render dashboard → **New** → **Blueprint** → pick the `wardrobe-ai` repo.
2. Render reads `render.yaml` and creates the web service. (There is no Render
   cron — the daily email runs on GitHub Actions; see step 8.)
3. In the web service env vars, paste:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`
   - `ANTHROPIC_API_KEY`
   - `APP_PASSWORD` (your chosen password)
   - `ALLOWED_ORIGINS` — for now: `http://localhost:5173` (we'll add the Vercel URL after step 5)
4. Other vars (OWM, Gmail, `SERPAPI_API_KEY`, `FEEDBACK_SECRET`) can be filled
   in as you enable those features — the backend boots fine without them.
   `FEEDBACK_SECRET` must match the value in GitHub Actions (see step 8).
5. First deploy will take ~3 min. Note the URL: `https://wardrobe-ai-backend.onrender.com` (or similar).
6. Test: `curl https://<your-render-url>/health` → should return `{"ok": true, "supabase": true, ...}`.

## 5. Deploy frontend to Vercel

1. Vercel → **Add New** → **Project** → import `wardrobe-ai` repo.
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
- Enter `APP_PASSWORD`. Should show "Connected ✅" and a JSON blob with `supabase: true`.
- Wrong password should show "Wrong password."

## 8. Daily email + weekly inference (GitHub Actions)

The recurring jobs run on **GitHub Actions**, not Render Cron (Render Cron needs
a paid plan). Add the Actions secrets and test the workflows following
[docs/daily-email.md](daily-email.md).

## Render free-tier note
Free web services sleep after 15 min idle and take ~30s to wake on first
request. That's fine for a personal app — and it doesn't affect the daily email,
which runs on GitHub Actions, not Render.
