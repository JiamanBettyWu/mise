# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Common commands

### Backend (FastAPI, run from `backend/`)
```bash
uv sync                                          # install deps
uv run uvicorn main:app --reload --port 8000     # dev server
uv run python test_graph.py                      # offline LangGraph checks (free, gitignored)
RUN_E2E=1 uv run python test_graph.py            # full pipeline (hits live APIs)
uv run python test_sampling.py                   # recency-decay sampler unit tests (pure, committed)
uv run python -m py_compile <file>               # quick syntax check
```

### Frontend (Vite + React, run from `frontend/`)
```bash
npm install
npm run dev      # serves on :5173
npm run build
npm run preview
```

### Daily-email job (run from repo root)
```bash
uv --project backend run python jobs/daily_outfit.py
```

### Other useful
- `gh pr create` / `gh issue create` — workflow is branch-per-issue, PR closes via `Closes #N`.
- `gh run view <id> --log` — fetch GitHub Actions run logs (the daily-outfit workflow runs every morning).

## Architecture: the "two AI pipelines" worth knowing

The backend has **two distinct AI flows**. Reading both before changing either saves time.

**1. Daily outfit recommender** — [`services/recommend.py`](backend/services/recommend.py)
A straight-line Python function: pull weather → load catalog → ask Claude to pick outfits for one or more "modes" (smart casual / athleisure / elevated). Used by `POST /outfits/today` and by the cron job. **Not a LangGraph.**

**2. Trip planner** — [`services/trip_planner.py`](backend/services/trip_planner.py)
A LangGraph `StateGraph` over a `PackingState` TypedDict:

```
get_weather → get_catalog → reason_and_select ──(has_gaps)──→ search_purchases ─┐
                                              ──(no_gaps )──────────────────────┴→ generate_output → END
```

- The graph is **compiled once at module load** (`_APP = build_graph()`) and reused across requests — see comment in `trip_planner.py`.
- `check_gaps` is a router function (returns a string label, doesn't mutate state); `add_conditional_edges` dispatches on it.
- Nodes return **partial state dicts** (`return {"weather": ...}`); they never mutate `state` in place. LangGraph merges the dict into the journal.
- `search_purchases_node` is currently a **stub** producing placeholder `PurchaseResult`s. Real search backend is tracked in [issue #10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10).

## Architecture: other things that take >1 file to see

**Auth.** A single shared password (`APP_PASSWORD` env) sent as `X-App-Password` header. The `require_password` dependency in [`backend/auth.py`](backend/auth.py) gates every router. Frontend stores it in `localStorage` and attaches it from [`frontend/src/services/api.js`](frontend/src/services/api.js).

**Supabase.** Single-tenant, **RLS disabled**, accessed with the **service_role key** server-side only. There's no row-level user context — this is a personal app. Lazy client in [`backend/db/supabase.py`](backend/db/supabase.py).

**Image pipeline (upload → tag).** Critical because Anthropic's vision API has a base64 size cap (5MB, which is ~3.5MB raw after base64 inflation), and Safari uploads HEIC that other browsers can't render.
1. Frontend best-effort downscales (see [`frontend/src/services/image.js`](frontend/src/services/image.js)).
2. Backend ALWAYS calls `services/image.ensure_under_limit()` — this **transcodes HEIC→JPEG and shrinks oversized images**. Same browser-safe bytes go to both Supabase Storage and Claude.
3. The mime type returned by `ensure_under_limit` drives the storage path extension (in `services/storage.py`) — don't trust the original filename's extension.

**Single .env at repo root.** Three Python entry points (`backend/main.py`, `backend/test_graph.py`, `jobs/daily_outfit.py`) all load it via explicit `Path(__file__).parents[1] / ".env"`. **Don't add a `backend/.env`** — the cwd-walking default of `load_dotenv()` causes silent divergence. See PR #11 for the cleanup that fixed it.

## Deploy surface

- **Backend** → Render (auto-deploy from `main`). Service config in [`render.yaml`](render.yaml).
- **Frontend** → Vercel (auto-deploy from `main`, root = `frontend/`). Config in [`frontend/vercel.json`](frontend/vercel.json).
- **Daily outfit cron** → **GitHub Actions** (NOT Render Cron — Render Cron requires a paid plan). Workflow: [`.github/workflows/daily-outfit.yml`](.github/workflows/daily-outfit.yml). Note: GitHub's scheduled runs are best-effort and routinely delayed 1–3h, which is why the workflow schedules at `20 8 * * *` UTC (offset early to compensate) with no exact-hour guard. See PR #7's commit for the diagnosis.

## Gotchas worth knowing

- **Python version parity.** Local `backend/.venv` is currently **3.14**; Render runs **3.11**. PEP 649 lazy annotations on 3.14 can silently hide `NameError`s that bite on Render at import time (we hit this with the schema class-order bug in PR #12). Tracked as [issue #13](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13). Until that lands, when adding model classes whose annotations reference other classes, define dependencies *before* consumers.
- **OWM `/forecast` is 5 days only.** Trips starting more than ~5 days out crash the weather node — tracked as [issue #9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9). For testing, pick dates inside the forecast window.

## Project conventions

- **Frontend design system is documented in [DESIGN.md](DESIGN.md).** Read it before any UI change. Update the principles, vocabulary, or decisions log in the same commit as the visual change — not in a follow-up.
- [`TODO.md`](TODO.md) is the "where I left off" scratchpad. **GitHub Issues and the Projects board are the source of truth** for tracked work; TODO.md is just the resume-pointer.
- **After each merged PR, update TODO.md and sweep it for stale info.** Move the shipped issue out of "Open issues", add it to the "Closed last session" line with the PR link, refresh "Where I left off" and "Next time I sit down" so the next session opens with a current pointer. Fix any line that referenced the now-shipped work as still pending.
- **Branch per issue**, named `feat/issue-N-...` or `fix/...`. PRs close issues with `Closes #N`.
- This is a solo repo; on PRs **skip the "Approve" step** (GitHub blocks self-approval) — use the green Merge button directly.
- Labels in use: `enhancement`, `bug`, `tech-debt`, `prompt-tuning`, `langgraph`.
