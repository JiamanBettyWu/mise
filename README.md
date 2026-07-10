# mise

*as in [mise en place](https://en.wikipedia.org/wiki/Mise_en_place) — everything
prepped before you need it. Here, it's your outfit that's ready before you're
awake enough to think about it.*

## It started in front of a closet

Standing in front of a visibly full rack, running late, thinking *"I have
nothing to wear"* — which was obviously false. The problem wasn't a shortage of
clothes; it was **decision fatigue**, the small daily tax of assembling an
outfit from scratch before the brain is fully online. So: outsource the
decision. That's the entire origin of this app.

The setup cost is one-time: photograph each piece of clothing and a vision
model tags it (type, color, formality, season, fabric, a rough warmth rating);
review, fix, save. After that:

- **☕ The morning email** — an outfit suggestion arrives before you're up,
  chosen for the actual weather and (optionally) your calendar, reasoned out in
  a sentence or two. Thumbs-up/down links in the email feed a learning loop.
- **✨ On-demand outfits** — for the days that aren't the default: describe the
  occasion ("dinner with friends after work, might rain") and generate
  suggestions for that context.
- **🧳 A trip packing planner** — destination + dates in, weather-appropriate
  packing list out; if the trip needs something you don't own, it flags the gap
  and goes shopping for it.
- **📈 A style learner** — a weekly background job reads the whole verdict
  history and distills it into durable, *editable* preferences ("leans toward
  neutral basics"), which feed back into generation.

The goal is a **warm start, not a verdict**: a plausible draft to react to
instead of a blank slate, plus the occasional pairing you'd never have tried
yourself. The app doesn't have to be right — only useful. That tolerance is
what lets it lean on randomness and learning instead of chasing correctness.

## Three AIs, one principle

"The AI" turned out to be three systems, because the three jobs have different
shapes:

1. **The daily recommender** — deliberately the least fancy: straight-line
   Python and one model call. Its cleverness is in *which clothes it lets the
   model see* (weighted sampling with recency + feedback).
2. **The trip planner** — a **LangGraph** agent, because packing spawns
   follow-up work at runtime (find a gap → go search for it).
3. **The style learner** — a second LangGraph doing the opposite job: not
   generating, but distilling feedback into preferences, with guardrails
   because a system that rewrites its own behavior can go quietly wrong.

They share one design principle:

> **Stochastic weights for preferences, deterministic logic for physics.**

Preferences are soft and accumulate — they belong in randomized, weighted
sampling where a wrong guess washes out and variety is a feature. Weather is
physics — "4°C and raining" gets a hard deterministic gate, because a parka
recommended on a hot day one time in twenty is the worst kind of bug:
unreproducible. Mixing the two up gives you either that, or an app so rigid it
suggests the same safe outfit forever.

The full architecture (the three pipelines, auth, image handling, deploy
surface) is documented in **[AGENTS.md](AGENTS.md)** — start there if you're
working on the code.

## The honest artifacts

If you enjoy seeing how a project actually gets built — as opposed to how it
looks once it's tidied up — this repo keeps two running records:

- **[SESSIONS.md](SESSIONS.md)** — a dated, session-by-session journal of what
  shipped and why.
- **[LEARNINGS.md](LEARNINGS.md)** — an unpolished chronological log of every
  gotcha that bit me, written while fresh.

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

Cheap was a constraint: this is a single-user personal app that costs **$1–2 a
month** to run, almost entirely model usage (metered by the app itself in a
small ledger table).

- **Backend** → Render (auto-deploy from `main`; config in [render.yaml](render.yaml)).
- **Frontend** → Vercel (auto-deploy from `main`, root = `frontend/`; config in
  [frontend/vercel.json](frontend/vercel.json)).
- **Daily outfit email** → **GitHub Actions** cron
  ([.github/workflows/daily-outfit.yml](.github/workflows/daily-outfit.yml)) —
  *not* Render Cron, which needs a paid plan; the same automation most people
  only use for tests makes a fine free scheduler. See [docs/daily-email.md](docs/daily-email.md).
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
