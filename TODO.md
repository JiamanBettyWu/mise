# TODO

The concise "what's next" for wardrobe-ai. **GitHub Issues** + the
**[Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/issues)** are the
source of truth for tracked work; this file is the forward-looking scratchpad.

- **Session history** (what got done, when) lives in **[SESSIONS.md](SESSIONS.md)**.
- **Conventions** (branch naming, solo-merge, labels, the post-PR doc sweep) live
  in [AGENTS.md](AGENTS.md) → "Project conventions".

> If a scratch idea matures, promote it to a GitHub Issue and delete the line.

---

## Current state

**As of 2026-07-04 (latest session):** #123 shipped (PR #130) — `trip_plan` now
uses structured outputs (`output_config.format` via `create_tracked_parsed`),
deleting the #120/#122 defensive parsing; two review findings (metering skipped
on invalid output, `content[0]` indexing) were fixed pre-merge. One optional
follow-up: the paid `--trials 3` before/after eval was skipped — run it if
variance numbers are wanted. Full detail lives in [SESSIONS.md](SESSIONS.md).

---

## Next time I sit down, pick one

1. **[#124](https://github.com/JiamanBettyWu/wardrobe-ai/issues/124)** —
   node-level SSE streaming for the trip planner: render the plan + gaps as
   soon as `reason_and_select` finishes, purchase results fill in last.
   Closes out #2 (max_tokens checked via Weave — ~1000 actual vs 2048 cap,
   left as-is; fake progress indicators superseded by real ones).
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
(catalog by categories), [#5](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)
(prepare repo for public release), [#13](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13)
(local Python → 3.11 parity; largely defanged by CI),
[#118](https://github.com/JiamanBettyWu/wardrobe-ai/issues/118) (recommender
offline eval: synthetic scenarios + cross-family LLM judge, after #120),
[#111](https://github.com/JiamanBettyWu/wardrobe-ai/issues/111) (LangGraph rep:
`Send` fan-out for per-gap purchase searches — learning value + per-gap Weave
spans, not perf). See the
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
