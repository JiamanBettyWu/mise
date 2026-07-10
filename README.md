# mise

A personal wardrobe assistant. Upload photos of your clothes once and Claude's
vision model auto-tags them; from there the app:

- **Daily outfit email** — a morning email recommending outfits for the day,
  weather-aware and (optionally) tailored to your calendar. Thumbs-up/down links
  in the email feed a learning loop.
- **Trip planner** — a LangGraph pipeline that takes a destination + dates,
  pulls the forecast, picks a packing list from your catalog, flags gaps, and
  suggests purchases to fill them.
- **Learns your taste** — feedback adjusts item sampling weights, and a weekly
  job distills your verdict history into editable style preferences.
- **Web app** — browse and manage the catalog (laundry / packed states), edit
  AI tags, generate today's outfit on demand, and manage your profile +
  preferences.

This is a single-user personal app. The architecture (the three AI pipelines,
auth, image handling, deploy surface) is documented in **[AGENTS.md](AGENTS.md)**
— start there if you're working on the code.

## Local development

### Backend
```bash
cd backend
uv sync
cp ../.env.example ../.env   # single .env at repo root; fill in values
uv run uvicorn main:app --reload --port 8000
uv run pytest                # offline test suite (free, no network)
```

### Frontend
```bash
cd frontend
npm install
echo "VITE_API_BASE_URL=http://localhost:8000" > .env.local
npm run dev
```

Open http://localhost:5173 and enter your `APP_PASSWORD` to unlock the UI.

### Diagnostics & evals (run from the repo root)
```bash
# Recommendation-diversity report over live outfit_history — read-only, free.
# --save writes a dated markdown report (+ JSON metrics footer) to
# backend/evals/reports/diversity/; commit it and compare runs with git diff.
uv --project backend run python backend/evals/diversity_report.py --exclude-default --save

# Offline evals (manual, paid — real Claude calls; results land in W&B Weave)
uv --project backend run python backend/evals/eval_recommend.py --trials 3
uv --project backend run python backend/evals/eval_trip.py
```

> **Config note:** there is a **single `.env` at the repo root** — every Python
> entry point loads it by an explicit path. Don't create a `backend/.env`
> (see AGENTS.md for why).

## Deployment

- **Backend** → Render (auto-deploy from `main`; config in [render.yaml](render.yaml)).
- **Frontend** → Vercel (auto-deploy from `main`, root = `frontend/`; config in
  [frontend/vercel.json](frontend/vercel.json)).
- **Daily outfit email** → **GitHub Actions** cron
  ([.github/workflows/daily-outfit.yml](.github/workflows/daily-outfit.yml)) —
  *not* Render Cron, which needs a paid plan. See [docs/daily-email.md](docs/daily-email.md).
- **Weekly preference inference** → GitHub Actions cron
  ([.github/workflows/infer-preferences.yml](.github/workflows/infer-preferences.yml)).

First-time setup and the env-var checklist live in [docs/deploy.md](docs/deploy.md).

## Repo layout

```
backend/    FastAPI app + services
  routers/    HTTP routes
  services/   AI pipelines, weather, email, image handling
  sql/        dated, idempotent Supabase migrations (run in SQL Editor)
  mcp_server/ MCP shopping server (learning track; off the production path)
  tests/      offline pytest suite
frontend/   React + Vite UI
jobs/       standalone scripts (daily email, weekly inference, backfills)
docs/       setup notes + design records
  history/    superseded planning docs, kept for the record
```

## Documentation map

- **[AGENTS.md](AGENTS.md)** — architecture + conventions; the source of truth.
- **[DESIGN.md](DESIGN.md)** — frontend design system (read before any UI change).
- **[docs/recommendation-algorithm.md](docs/recommendation-algorithm.md)** — how the daily recommender works.
- **[docs/feedback-loop-design.md](docs/feedback-loop-design.md)** — why the feedback loop is built the way it is.
- **[LEARNINGS.md](LEARNINGS.md)** — running log of non-obvious gotchas.
- **[TODO.md](TODO.md)** — concise "what's next" (GitHub Issues are the real tracker).
- **[SESSIONS.md](SESSIONS.md)** — dated journal of what got done each session.
