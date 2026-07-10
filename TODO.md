# TODO

The concise "what's next" for mise. **GitHub Issues** + the
**[Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/issues)** are the
source of truth for tracked work; this file is the forward-looking scratchpad.

- **Session history** (what got done, when) lives in **[SESSIONS.md](SESSIONS.md)**.
- **Conventions** (branch naming, solo-merge, labels, the post-PR doc sweep) live
  in [AGENTS.md](AGENTS.md) → "Project conventions".

> If a scratch idea matures, promote it to a GitHub Issue and delete the line.

---

## Current state

**As of 2026-07-09 (latest session):** the repo is **PUBLIC and renamed to
`mise`** (#5 closed; #125 repo-level items done — remaining: local folder
rename + `.mcp.json` path, Render/Vercel dashboard verification, cosmetic
sweep PR). Earlier same day: #143 shipped (PR #147 + follow-up #148) — config
cohort labels on `outfit_history`, prompt-registry CI guard, Weave
StringPrompt publishes in both eval launchers.
**Open manual follow-ups:** re-run `diversity_report.py --exclude-default
--save` in a few weeks and diff against the 2026-07-09 report (now with
cohort labels); the local backend dev server is running with
`SKIP_PURCHASE_SEARCH=1` set — restart it without that env var when real
SerpAPI results are wanted again. Full detail lives in
[SESSIONS.md](SESSIONS.md).

---

## Next time I sit down, pick one

1. **Re-run `diversity_report.py --exclude-default --save` (~late July)** and
   git-diff against `backend/evals/reports/diversity/2026-07-09.md` — confirm
   the #135 fix breaks the satin-skirt alternation in production (watch
   bottoms entropy 0.902, median gap 3d, % repeats ≤3d 61%).
2. **[#86](https://github.com/JiamanBettyWu/wardrobe-ai/issues/86)** —
   MCP stretch: Streamable HTTP transport + `langchain-mcp-adapters` into a
   LangGraph node — the part most transferable to the work MCP project.
3. **Let the weekly inference job (#62) accumulate, and curate it.** The Sunday
   cron (`20 1 * * 1`) re-derives inferred prefs from the whole verdict history
   each week — keep clicking/tagging thumbs; volume is the whole game. Each week
   glance at Profile → *Learned from your feedback*: dismiss any statement that
   doesn't ring true (that **tombstones** it — the job won't re-emit it), or
   "Edit & own" to promote it to a hard pref. The "reviewed N days ago"
   heartbeat flags if the cron ever stops.
4. **Confirm inferred prefs actually shift generation** — they ride the prompt as
   *soft* "Learned preferences", so watch whether athleisure picks drift toward
   open footwear over the next several days. Lever if too weak/strong: the
   "Learned preferences" bullet in `claude.py`.
5. **Check the first real-event morning for #64's events path** — the empty-day
   path is verified live; on a morning with calendar events the Actions log
   should show `calendar: N event(s) → modes: …` and the email should carry the
   📅 explanation line.
6. **The sport-sandal experiment** (decided 2026-06-12): the footwear floor
   works; the model just keeps *choosing* the sandal. Plan: tag the sandal with a
   `specific_items` 👎 when it's a bad pick and let the multiplier suppress it.
   If it still dominates after a few tagged verdicts, the principled fix is
   `SMALL_CATEGORY_MAX` 5→4 in `outfit_history.py`. NB: the first #62 run *liked*
   the sandal in athleisure — keep the experiment scoped to Elevated/dressy.
7. **Spot-check inferred warmth values in the catalog UI** — open a handful of
   items and correct any rating that looks off (corrections stick; backfill never
   overwrites non-null). The prompt reasons over these numbers daily (#18).
8. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — tune trip
   planner prompts after a real trip (best done *after* actually using the
   planner for Oaxaca).

Other tracked-but-not-urgent: [#1](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
(catalog by categories), [#125](https://github.com/JiamanBettyWu/mise/issues/125)
(finish the mise rename: local folder, `.mcp.json`, cosmetic sweep),
[#13](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13)
(local Python → 3.11 parity; largely defanged by CI),
[#136](https://github.com/JiamanBettyWu/wardrobe-ai/issues/136) (cross-family
LLM judge + thumbs calibration, split from the now-shipped #118; learning-track),
[#111](https://github.com/JiamanBettyWu/wardrobe-ai/issues/111) (LangGraph rep:
`Send` fan-out for per-gap purchase searches — learning value + per-gap Weave
spans, not perf),
[#144](https://github.com/JiamanBettyWu/wardrobe-ai/issues/144) (email
one-tap refine links) + [#145](https://github.com/JiamanBettyWu/wardrobe-ai/issues/145)
(multi-turn refinement in the UI — the checkpointer LangGraph rep; same
feature, two front doors),
[#146](https://github.com/JiamanBettyWu/wardrobe-ai/issues/146) (Insights
dashboard: drift trends + usage, multi-user-ready). See the
[Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/issues) for status.

---

## Scratch — not yet promoted

Things I might do but aren't worth an issue yet. Move up to Issues when they
firm up.

- **Option A multi-photo upload** (select N photos, one item per photo) — sibling
  of [#24](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)'s B-lite path.
  File separately if pursued.
- V2 ideas (deferred from trip planner spec): day-by-day outfits,
  multi-destination.

---

## Larger plans (not in the issue tracker yet)

Plans too big for a single issue. Each gets split into a sequence of issues/PRs
when we're ready.

- **[Multi-user support](docs/multi-user-plan.md)** — let 3-5 friends use their
  own wardrobes. Deferred until the "friend-ready" milestone (see doc for the
  gating checklist).
