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

### 2026-06 — Global `button:hover` outranks a bare `.chip` (CSS specificity)
Styled toggle chips as `<button class="chip">`, but a "Packed" chip flashed white on hover. Cause: the global `button:hover` (element + pseudo-class = 0,1,1) outranks `.chip` (one class = 0,1,0). Lesson: any class-based component style built on a global element selector needs its *own* `:hover`/state rules (`.chip:hover` = 0,2,0) to win — base specificity isn't enough once a pseudo-class enters the global rule.

### 2026-06 — Private repos can't inline raw images in PR descriptions
Committed a mockup PNG and tried to embed it via `blob/<sha>/...?raw=true` and `raw.githubusercontent.com` — both 404 because the repo is private and GitHub's camo proxy can't authenticate to raw. The only way to inline-render an image in a private-repo PR is to drag-drop it into the description in the browser (uploads to the signed `user-attachments` CDN). From the CLI you can only *link* to a committed file, not embed it.

### 2026-06 — A *hanging* import (not an error) can mean corrupted site-packages
Backend wouldn't start: `uvicorn` hung silently. Bisected with `signal.alarm` and found `import dotenv` hanging forever. Cause wasn't code — `.venv/lib/.../dotenv/*.py` were full of NUL bytes (filesystem corruption; `ls` even showed `total 0` blocks). A read on unallocated/bad blocks *blocks on I/O* instead of erroring, so the import hangs rather than throwing. Same event had corrupted `frontend/node_modules`. Fix: rebuild from lockfiles — `uv sync` / `npm ci`. Lesson: hanging import + recently-flaky disk → scan the package files for NUL bytes (`grep -qU $'\x00'`), don't debug the code.

### 2026-06 — Don't run `uvicorn --reload` right after `uv sync` (it watches `.venv`)
After rebuilding `.venv`, started the backend with `--reload`. WatchFiles watches the whole project *including `.venv`*, so `uv sync`'s freshly-written files kept triggering reloads that reset in-flight connections — auth requests returned `000`/curl-exit-56 even though the server logged `200`. Looked like an auth bug; was really restart-churn. For dev that needs reload, exclude the venv: `--reload-exclude '.venv/*'`. Or just run without `--reload` when you're not editing backend code.
