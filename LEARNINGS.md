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

### 2026-06 — UPDATE: the "corruption" was iCloud eviction, not a bad disk
Follow-up to the two entries above. Root cause found: the repo lived on `~/Desktop`, which is synced by iCloud "Desktop & Documents" with "Optimize Mac Storage" on. iCloud was *evicting* file contents to the cloud (files go `dataless` — size shown, 0 local blocks). Reading an evicted file triggers an on-demand download; when that stalls you get a hang (kernel stuck on import), and partial/failed fetches looked like NUL corruption. `verifyVolume /` came back clean and SMART was healthy — because the disk was always fine. Tells: `ls` shows `total 0` blocks; `find <dir> -type f -flags +dataless` lists evicted files. Fix: moved the repo to `~/dev` (outside iCloud). NEVER keep repos/`node_modules`/`.venv` in Desktop or Documents when iCloud sync is on.

### 2026-06 — Scarce categories + recency decay can force absurd picks (sports sandals for Elevated)
Elevated mode recommended sports sandals. Likely mechanism: I own few dressy shoes, they were recommended yesterday, so the recency penalty plus the global 0.7 pool sample left no suitable shoes for Claude to pick — and it picked *something* instead of using the skip convention. Lesson: per-item diversity machinery needs category awareness — rotation pressure only makes sense when substitutes exist. Fix scoped in docs/feedback-loop-design.md (D6/D7); relates to #16. Postscript: the catalog query showed only ONE elevated-capable pair of shoes among 5 footwear items — and the outfit prompt *mandated* shoes in every outfit, so the model's least-bad compliance was sport sandals. The prompt now allows omitting a slot.

### 2026-06 — Long trip prompts can truncate Claude JSON, then look like parser bugs
A 17-day trip hit `JSONDecodeError: Unterminated string...`; root cause was Claude stopping inside a JSON string because the packing-plan response cap was too low. Fix: raise `max_tokens` for larger structured outputs and make `parse_json()` report `stop_reason`, length, and text snippets so truncation is obvious next time.

### 2026-06 — Recency, multipliers, and repeat-dedup are three jobs, not redundancy
Almost "simplified" the sampler by replacing recency weighting with a hardcoded "block recent repeats" check (#17). They operate at different granularity: #17 blocks *set-level* repeats — which are rare, with a 45-item pool exact collisions almost never happen; recency rotates *items* — the repetition you actually feel day-to-day is one item recurring across ever-different outfits (see the sport-sandal saga, which happened precisely because footwear is exempt from recency); and the beta-Bernoulli multipliers learn *taste* from verdicts. Recency also doubles as the exploration half of an explore/exploit loop — the multipliers can only learn about items that get airtime, so killing rotation would starve the preference learner of data. Each layer covers a hole the other two can't. Decided same day: ship #17 as an exact-set extension of the #63 blocked_combos filter; Jaccard-overlap blocking deliberately rejected as over-engineering until near-miss repeats actually show up.

### 2026-06 — "Re-derive each run" + no DB transaction = delete-then-insert can wipe everything
Building the weekly preference-inference job (#62): the inferred prefs are re-derived from scratch every run, which tempts you to *delete the active set, then insert the fresh one*. But PostgREST gives no transaction — if the Claude call or JSON parse throws *after* the delete, you've wiped every inferred pref the user hadn't yet edited and inserted nothing. Two fixes, both load-bearing: (1) only mutate on success — a failed call must abort with the table untouched, and a *failed* call is not the same as an *empty* inference (the latter is a legitimate "no patterns yet" wipe); (2) insert-then-delete-old, not the reverse — ordering is the only atomicity lever you have, so a mid-run crash leaves a stale-but-present (or briefly duplicated, self-healing next week) set, never empty. General rule: when "regenerate from scratch" meets a transactionless store, write-then-prune beats prune-then-write.

### 2026-06 — "Return ONLY JSON" is a request, not a guarantee — parse at the chokepoint, not the prompt
First live run of the #62 inference job failed: Sonnet narrated its analysis in prose first ("I need to find patterns...") and put the actual JSON in a ```json fence at the *end*. `parse_json` only stripped a fence when the response *started* with ```, so `json.loads` choked on the leading prose — looked like a model failure, was really a parser assumption. The graph's atomicity design held perfectly (infer raised → upsert never ran → prefs table untouched, a failed run cost nothing), so the only damage was a red Actions run. Fix: made `parse_json` tolerant via `_extract_json` — first ```json fence anywhere, else first-`{`-to-last-`}` span — instead of tightening the prompt. Reasoning-capable models narrate before answering; the durable fix is a forgiving parser at the shared chokepoint (helps the outfit/trip pipelines too), not a stricter instruction the model can still ignore.

### 2026-06 — A stdio MCP server looks frozen because it *is* waiting — there's no argv
First FastMCP server (#79). Ran `python -m mcp_server.shopping_server` expecting output; got a blank, looked hung. It wasn't — a stdio MCP server is a *server*, not a CLI: it blocks reading JSON-RPC from stdin until a client speaks, exactly like a web server sitting idle with no requests. Silence = healthy. There is no command-line argument interface; arguments arrive as `call_tool("name", {dict})` from a client (the `mcp dev` Inspector, Claude Desktop, or an `mcp` ClientSession), never as argv. To actually see it work, drive it from a client.

### 2026-06 — Launch a package-based MCP server with `--directory ... -m pkg.mod`, and never name the dir `mcp/`
Same session as above. The server does `from services.search import ...`, so it only resolves when `backend/` is the import root. `python path/to/shopping_server.py` puts the *file's* dir on `sys.path[0]`, not backend — `services` vanishes. Fix: launch as a module from backend: `uv run --directory <repo>/backend python -m mcp_server.shopping_server` (this is also the exact `command`/`args` Claude Desktop needs, with an absolute `uv` path since the app doesn't inherit your shell PATH). Related trap I dodged up front: the folder must NOT be named `mcp/` — a top-level `mcp` package shadows the installed `mcp` SDK, and your own `from mcp.server.fastmcp import FastMCP` would import your folder instead. Named it `mcp_server/`.

### 2026-06 — "mcp vs fastmcp" is a false split — it's one SDK with two layers
Confused myself wiring the Phase 3 client (#79): why import server stuff from `mcp.server.fastmcp` but the client from `mcp`? They're the *same installed package*. `FastMCP` is the high-level **server-authoring** helper bundled inside the official `mcp` SDK (decorators + type-hints → tool schema); `ClientSession` (+ `mcp.client.stdio.stdio_client`) is that SDK's **standard client** — the canonical way to *consume* a server. There's no "FastMCP client" in the official SDK; FastMCP is a server abstraction, wrong layer for the client. Landmine for later: there's *also* a separate third-party PyPI package literally named `fastmcp` ("FastMCP 2.0", a superset that grew out of the donated code) which *does* ship a `Client` — so check whether an example imports `from mcp.server.fastmcp …` (official) or `from fastmcp …` (standalone 2.0); they're not the same project.

### 2026-06 — MCP clients are async because the protocol is bidirectional, not just request/response
Why is the whole client (`stdio_client`, `ClientSession`, `main`) wrapped in async? Because MCP isn't strict call-and-return: while you await a tool result, the server can push notifications/progress/sampling requests back at you. So the client runs a background reader task that routes incoming messages *concurrently* with your awaited `call_tool` — two things happening in one program, which is exactly what an event loop is for. Hence `async with` (async spawn + clean async subprocess teardown), `await initialize/call_tool` (yield to the loop during I/O waits), and `asyncio.run(main())` to drive it. Mental model: synchronous = stare at the wall till your food's ready; async = take a buzzer so the kitchen can ping you mid-wait.

### 2026-06 — Don't MCP-wrap your own in-process function to call it from your own graph
The tempting next step after #79 was to route `search_purchases_node` through the new MCP server. It's all cost, no benefit: the server is plain Python in the *same process* as the LangGraph, so going through MCP means spawn-a-subprocess + JSON-RPC-serialize-args + deserialize + run + serialize-back — to reach a function you could call directly. That's precisely why the #79 guardrail keeps production as `node → services/search.py` and parks the MCP server off to the side. MCP earns its keep across a *boundary* — another process, language, team, or a tool you don't own — or when you want an agent to discover/choose among many tools (the `langchain-mcp-adapters` path). Bonus proof of the "write once, any host" payoff: the same unchanged `shopping_server.py` is callable from Claude Desktop, the demo client, *and* Claude Code (via a committed project-scoped `.mcp.json`).

### 2026-06 — Secrets in query-string params leak via httpx INFO logging — fix the logger, not the call site
Running the #79 MCP tool printed my SerpAPI key in plain text — httpx logs the *full request URL* at `INFO`, and SerpAPI (like OpenWeatherMap's `appid`) requires the key as a `?api_key=` query param, so the secret rides in the URL. `weather.py` had the same vector in three places. Two non-obvious bits: (1) the leak is httpx's logger, not mine — `weather.py` doesn't even import `logging`, but `logging.getLogger("httpx")` is a *global, name-keyed* logger httpx writes to regardless, so the fix (`logging.getLogger("httpx").setLevel(logging.WARNING)`) reaches up and silences httpx with no local logger needed. (2) Rotating the key alone is treating the symptom — the *behavior* re-leaks the new key on its next call, so deploy the logging fix FIRST, then rotate. Neither API supports a header alternative, so you can't keep the key out of the URL — only out of the logs. General rule: secrets in URLs leak through every layer that logs URLs (app logs, proxies, browser history); prefer headers, and when forced into the query string, silence URL logging at the client.
