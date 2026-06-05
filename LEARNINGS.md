# Learnings

Freeform log of things I figured out the hard way. Append-only, chronological, two-line entries are great. The point is frictionlessness — write the entry while it's fresh, don't polish.

Future-me uses this to remember what was actually hard, for blog posts and interviews. Today-me uses it to avoid relearning the same lesson.

---

## 2026

### 2026-06 — Legacy GitHub Pages builds silently break on dormant repos
The `username.github.io` repo I hadn't touched since 2021 stopped triggering Pages builds on push. POSTing a build manually returned `queued`, but the job never actually ran. Fix: switch the Pages source from "legacy" (the old Jekyll pipeline) to "GitHub Actions" and add a workflow with `actions/deploy-pages@v4`. The Actions-based pipeline is the modern default anyway.

### 2026-06 — GitHub Actions scheduled crons drift 1–3h late routinely
The daily-outfit job schedules at `20 8 * * *` UTC, intentionally early, with no exact-hour guard. GitHub's scheduled runs are best-effort and routinely delayed — assuming on-the-minute precision would have broken the morning email.

### 2026-06 — Python 3.14 hides `NameError`s that bite on Render (3.11)
PEP 649 lazy annotation evaluation on 3.14 silently tolerated a schema class-order bug locally. On Render's 3.11, the same code threw `NameError` at import time. Workaround until I align versions: define dependent classes *before* consumers — don't rely on lazy evaluation.

### 2026-06 — One `.env` at the repo root, loaded explicitly
Three Python entry points (backend, test, jobs) used to walk the cwd to find `.env`, which caused silent divergence depending on where I ran them from. Fix: every entry point does `load_dotenv(Path(__file__).parents[N] / ".env")` — explicit path, no walking. Convenience defaults are how you lose an afternoon.

### 2026-06 — Anthropic vision API has a base64 size cap (~5MB → ~3.5MB raw)
Base64 inflates ~33%, so the practical raw-image cap is around 3.5MB. Safari also uploads HEIC by default, which most browsers can't render. The server-side `ensure_under_limit()` does both jobs (transcode HEIC → JPEG, shrink to fit) and the *same* bytes go to both Supabase Storage and Claude. Mime type drives the storage path extension — don't trust the filename.

### 2026-06 — LangGraph: nodes return partial state, never mutate
Idiomatic LangGraph nodes return `{"key": value}` partial dicts and let the framework merge into the journal. Mutating `state` in place works locally but breaks when the graph is checkpointed/resumed. Routers (like `check_gaps`) return a *string label*, not a state mutation — `add_conditional_edges` dispatches on the label.

### 2026-06 — Compile the LangGraph once at module load, not per request
`_APP = build_graph()` at module scope, called once. Re-compiling per request wastes hundreds of ms. Once is fine because the graph is user-agnostic — state is passed in via `invoke()`.

### 2026-06 — Frontend persistence pattern: hydrate on mount, sync via `useEffect`
For "where I left off" state across nav (TripPlan, TodayOutfit), the shape that works: `hydrate()` runs on mount with silent expiry (drop stale payloads); a `useEffect` syncs to `localStorage` on every change; empty form removes the key entirely. Don't persist things that are cheap to re-fetch (geolocation) or that go stale fast (yesterday's outfit).
