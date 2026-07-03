# AGENTS.md

This file provides guidance to coding agents (e.g. Claude Code, Codex) when working with code in this repository.

## Common commands

### Backend (FastAPI, run from `backend/`)
```bash
uv sync                                          # install deps
uv run uvicorn main:app --reload --port 8000     # dev server
uv run pytest                                    # offline test suite in tests/ (free, no network)
RUN_E2E=1 uv run pytest                          # + the full trip-planner pipeline (hits live APIs)
uv run black .                                   # format backend Python
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

### One-off scripts (run from repo root)
```bash
uv --project backend run python jobs/backfill_warmth.py --dry-run   # warmth backfill (#40); drop --dry-run to write
```

### Other useful
- `gh pr create` / `gh issue create` — workflow is branch-per-issue, PR closes via `Closes #N`.
- `gh run view <id> --log` — fetch GitHub Actions run logs (the daily-outfit workflow runs every morning).

## Architecture: the AI pipelines worth knowing

The backend has **three distinct AI flows**. Reading the relevant one before changing it saves time. Two are LangGraphs (trip planner, preference inference); the daily recommender is plain straight-line Python.

**1. Daily outfit recommender** — [`services/recommend.py`](backend/services/recommend.py)
A straight-line Python function: pull weather → load catalog → extremes gate ([`services/weather_gate.py`](backend/services/weather_gate.py), drops warmth-absurd items, #18) → weighted sampling ([`services/outfit_history.py`](backend/services/outfit_history.py); weight = recency (#15/#44) × feedback multiplier from thumbs verdicts (#42), pool topped up to per-category floors (#16)) → ask the model to pick outfits for one or more "modes" (smart casual / athleisure / elevated). Used by `POST /outfits/today` and by the cron job. The cron job's modes are calendar-driven when the optional `CALENDAR_ICS_URL` Actions secret is set ([`services/calendar.py`](backend/services/calendar.py), #64): no events today → Smart casual only, otherwise a Haiku call maps events to modes (floor mode always included; any failure → all three modes). Secret unset = toggle off, hardcoded three modes. Verdicts arrive via emailed 👍/👎 links (#39) or the web thumbs on TodayOutfit (#41) — same `outfit_history.feedback` column either way. **Not a LangGraph.** Full algorithm reference with formulas, constants, and worked examples: [docs/recommendation-algorithm.md](docs/recommendation-algorithm.md).

**2. Trip planner** — [`services/trip_planner.py`](backend/services/trip_planner.py)
A LangGraph `StateGraph` over a `PackingState` TypedDict:

```
START ─┬→ get_weather → infer_weather_if_needed ─┐
       └→ get_catalog ───────────────────────────┴→ reason_and_select ──(has_gaps)──→ plan_purchase_queries → search_purchases ─┐
                                                                       ──(no_gaps )──────────────────────────────────────────────┴→ generate_output → END
```

- The graph is **compiled once at module load** (`_APP = build_graph()`) and reused across requests — see comment in `trip_planner.py`.
- `check_gaps` is a router function (returns a string label, doesn't mutate state); `add_conditional_edges` dispatches on it.
- Nodes return **partial state dicts** (`return {"weather": ...}`); they never mutate `state` in place. LangGraph merges the dict into the journal.
- `infer_weather_if_needed_node` only calls Claude for partial/missing forecast coverage; full forecasts pass through unchanged.
- The weather and catalog branches **fan out from START** and have unequal lengths, so the join uses the list form `add_edge(["infer_weather_if_needed", "get_catalog"], "reason_and_select")` — naive per-edge joins would fire `reason_and_select` a superstep early (#2).
- `plan_purchase_queries_node` makes one lightweight **Haiku** call per trip to turn gaps into concise Google Shopping queries, using `profile.shopping_department` plus applicable preferences. If planning fails, it falls back to deterministic `{department} + {gap.item}` queries. (The main `reason_and_select` call deliberately stays on Sonnet.)
- `search_purchases_node` is best-effort and **concurrent** (per-gap searches run in a thread pool, #107): any per-query failure or empty result keeps that gap visible with `results=[]`, so the packing plan still renders.

**3. Weekly preference inference** — [`services/preference_inference.py`](backend/services/preference_inference.py)
A LangGraph `StateGraph` over an `InferenceState` TypedDict, run from a weekly GitHub Actions cron ([`jobs/infer_preferences.py`](jobs/infer_preferences.py), [`.github/workflows/infer-preferences.yml`](.github/workflows/infer-preferences.yml)):

```
fetch ──> check_evidence ──(enough)──> infer ──> validate ──> upsert ──> END
                          └──(too few)──────────────────────────────────> END
```

It reads the full outfit-verdict history (with #60 attribution + weather + notes) and distills durable style preferences into the `preferences` table as `source = 'inferred'`, **re-derived from scratch each run** (#62). Those rows then feed generation and render/edit in the profile UI (#61). No new migration: the `preferences` schema (`source`/`status`/`evidence_ids`) was built for this in #61. **Inferred prefs feed the prompt as SOFT preferences, distinct from user-authored ones:** `recommend._get_active_preferences()` returns `(user, inferred)` split by source, and `claude.py` renders two blocks — "User preferences" (hard constraint) and "Learned preferences" (nudge, may be wrong, loses to a hard pref on conflict). A wrong inference therefore degrades gracefully instead of binding every outfit.

Things that bite if you don't know them (full rationale in D8 of [docs/feedback-loop-design.md](docs/feedback-loop-design.md)):
- **A wrong inferred pref is a systematic bias with no floor** (unlike the numeric multiplier loop, which self-corrects). The editable UI is the only floor, so inferred prefs MUST be legible — short, specific, each citing the `outfit_history` rows behind it via `evidence_ids`.
- **`upsert_node` inserts the fresh set BEFORE deleting the prior ids** — PostgREST has no transaction, so ordering is the only atomicity lever. A failed run leaves the old set present, never empty; the graph only reaches `upsert` if the Claude call + parse succeeded.
- **The model cites evidence by 1-based index, not UUID** (UUIDs are token-heavy and mis-transcribed); `validate_node` maps indices → real ids and drops statements below the evidence floor or colliding with a rejected tombstone.
- A failed weekly run **costs nothing** — that's why this is the low-risk place for LangGraph reps, and why nodes can just raise.
- **Heartbeat:** a successful `run()` stamps `profile.preferences_reviewed_at`; a failure leaves it stale, and the Profile UI shows it as relative time ("reviewed 9 days ago"). Health is surfaced as staleness, not a failure log — that's the only signal that also catches a silently-disabled cron (GitHub disables scheduled workflows after 60 days of no commits).

## Architecture: other things that take >1 file to see

**Auth.** A single shared password (`APP_PASSWORD` env) sent as `X-App-Password` header. The `require_password` dependency in [`backend/auth.py`](backend/auth.py) gates every router. Frontend stores it in `localStorage` and attaches it from [`frontend/src/services/api.js`](frontend/src/services/api.js).

**Supabase.** Single-tenant, **RLS disabled**, accessed with the **service_role key** server-side only. There's no row-level user context — this is a personal app. Lazy client in [`backend/db/supabase.py`](backend/db/supabase.py).

**Image pipeline (upload → tag).** Critical because Anthropic's vision API has a base64 size cap (5MB, which is ~3.5MB raw after base64 inflation), and Safari uploads HEIC that other browsers can't render.
1. Frontend best-effort downscales (see [`frontend/src/services/image.js`](frontend/src/services/image.js)).
2. Backend ALWAYS calls `services/image.ensure_under_limit()` — this **transcodes HEIC→JPEG and shrinks oversized images**. Same browser-safe bytes go to both Supabase Storage and the vision model.
3. The mime type returned by `ensure_under_limit` drives the storage path extension (in `services/storage.py`) — don't trust the original filename's extension.

**Single .env at repo root.** Every Python entry point (`backend/main.py`, `backend/tests/conftest.py`, the `jobs/` scripts) loads it via an explicit path relative to `__file__`, never cwd. **Don't add a `backend/.env`** — the cwd-walking default of `load_dotenv()` causes silent divergence. See PR #11 for the cleanup that fixed it.

## Deploy surface

- **Backend** → Render (auto-deploy from `main`). Service config in [`render.yaml`](render.yaml).
- **Frontend** → Vercel (auto-deploy from `main`, root = `frontend/`). Config in [`frontend/vercel.json`](frontend/vercel.json).
- **CI** → GitHub Actions runs the offline pytest suite on every PR and push to `main` ([`.github/workflows/tests.yml`](.github/workflows/tests.yml)). Pinned to **Python 3.11 to match Render** — it's the guard against the 3.14/3.11 annotation gotcha below. No secrets needed; the `RUN_E2E` test self-skips.
- **Daily outfit cron** → **GitHub Actions** (NOT Render Cron — Render Cron requires a paid plan). Workflow: [`.github/workflows/daily-outfit.yml`](.github/workflows/daily-outfit.yml). Note: GitHub's scheduled runs are best-effort and routinely delayed 1–3h, which is why the workflow schedules at `20 8 * * *` UTC (offset early to compensate) with no exact-hour guard. See PR #7's commit for the diagnosis.
- **Email feedback links (#39)** → `FEEDBACK_SECRET` must be identical in **three places**: repo-root `.env`, Render env, GitHub Actions secrets. The daily job *signs* tokens in-process on the Actions runner; Render only *verifies* — a mismatch makes every emailed 👍/👎 link 400. The job also needs `BACKEND_PUBLIC_URL` (Actions secret) to build the links.
- **Calendar-driven modes (#64)** → optional `CALENDAR_ICS_URL` Actions secret holding the Google Calendar "secret address in iCal format" URL. **Presence of the secret IS the toggle.** Known limitation: Google caches the ICS feed, so same-morning calendar additions can lag hours; events scheduled days ahead are fine.

## Gotchas worth knowing

- **Python version parity.** Local `backend/.venv` is currently **3.14**; Render runs **3.11**. PEP 649 lazy annotations on 3.14 can silently hide `NameError`s that bite on Render at import time (we hit this with the schema class-order bug in PR #12). Tracked as [issue #13](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13). Until that lands, when adding model classes whose annotations reference other classes, define dependencies *before* consumers. The CI test workflow runs on 3.11, so import-time breakage of anything the tests touch is caught on the PR rather than on Render.
- **OWM `/forecast` is 5 days only.** Trips outside that live window now use explicit coverage metadata plus a model-generated trip-level climate estimate (PR #38). For tests that need real forecast data, pick dates inside the OWM window; for fallback behavior, test partial/out-of-window dates.

## Project conventions

- **Session start:** read TODO.md's "Current state" pointer first — it carries
  open manual follow-ups (e.g. pending key rotations) and what just shipped.
  Read the latest SESSIONS.md entry too when the task builds on recent work or
  the session is open-ended ("what's next"); for a scoped issue, the issue body
  is the source of truth and usually suffices.
- **Frontend design system is documented in [DESIGN.md](DESIGN.md).** Read it before any UI change. Update the principles, vocabulary, or decisions log in the same commit as the visual change — not in a follow-up.
- **Two complementary files, kept lean:** [`TODO.md`](TODO.md) is the concise *forward-looking* "what's next" (current-state pointer + the "Next time I sit down" list + scratch/larger plans). [`SESSIONS.md`](SESSIONS.md) is the *backward-looking* journal — one dated entry per working session plus the closed-PR ledger. **GitHub Issues and the Projects board are the source of truth** for tracked work; these two files are just pointers.
- **After each merged PR:** (1) **append** a new dated entry at the top of `SESSIONS.md` (narrative of what shipped + PR link) and add the issue to its closed-PR ledger; (2) **refresh** `TODO.md` — update the "Current state" pointer and the "Next time I sit down" list, and remove any line that referenced the now-shipped work as still pending. **Keep the long narrative in SESSIONS.md, not TODO.md** — TODO.md stays short. The "Current state" pointer is **~3 sentences max** (latest session + any open manual follow-up, then link to SESSIONS.md); anything longer belongs in SESSIONS.md.
- **When you hit a non-obvious gotcha while debugging, append a 2-line entry to [LEARNINGS.md](LEARNINGS.md).** Informal, first-person, chronological. The file is intentionally unpolished — frictionlessness > documentation quality. Three years of accumulated entries is the real portfolio material.
- **Branch per issue**, named `feat/issue-N-...` or `fix/...`. PRs close issues with `Closes #N`.
- This is a solo repo; on PRs **skip the "Approve" step** (GitHub blocks self-approval) — use the green Merge button directly.
- Labels in use: `enhancement`, `bug`, `tech-debt`, `prompt-tuning`, `langgraph`.
