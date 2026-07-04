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

**As of 2026-07-04 (latest session):** #122 shipped (PR #129) — the last
bare-lookup spot in `reason_and_select_node` (item_ids/reasoning/essentials)
now defaults safely instead of KeyError→500, closing out the #120 validation
survey's follow-ups. #123 (structured-outputs pilot) is next. No open manual
follow-ups. Full detail lives in [SESSIONS.md](SESSIONS.md).

---

## Next time I sit down, pick one

1. **[#123](https://github.com/JiamanBettyWu/wardrobe-ai/issues/123)** —
   structured-outputs pilot on `trip_plan` (`output_config.format` makes
   malformed output impossible by construction); pairs with the #30/#120
   eval discipline.
2. **[#124](https://github.com/JiamanBettyWu/wardrobe-ai/issues/124)** —
   node-level SSE streaming for the trip planner: render the plan + gaps as
   soon as `reason_and_select` finishes, purchase results fill in last.
   Closes out #2 (max_tokens checked via Weave — ~1000 actual vs 2048 cap,
   left as-is; fake progress indicators superseded by real ones).
3. **[#86](https://github.com/JiamanBettyWu/wardrobe-ai/issues/86)** —
   MCP stretch: Streamable HTTP transport + `langchain-mcp-adapters` into a
   LangGraph node — the part most transferable to the work MCP project.
4. **Let the weekly inference job (#62) accumulate, and curate it.** The Sunday
   cron (`20 1 * * 1`) re-derives inferred prefs from the whole verdict history
   each week — keep clicking/tagging thumbs; volume is the whole game. Each week
   glance at Profile → *Learned from your feedback*: dismiss any statement that
   doesn't ring true (that **tombstones** it — the job won't re-emit it), or
   "Edit & own" to promote it to a hard pref. The "reviewed N days ago"
   heartbeat flags if the cron ever stops.
5. **Confirm inferred prefs actually shift generation** — they ride the prompt as
   *soft* "Learned preferences", so watch whether athleisure picks drift toward
   open footwear over the next several days. Lever if too weak/strong: the
   "Learned preferences" bullet in `claude.py`.
6. **Check the first real-event morning for #64's events path** — the empty-day
   path is verified live; on a morning with calendar events the Actions log
   should show `calendar: N event(s) → modes: …` and the email should carry the
   📅 explanation line.
7. **The sport-sandal experiment** (decided 2026-06-12): the footwear floor
   works; the model just keeps *choosing* the sandal. Plan: tag the sandal with a
   `specific_items` 👎 when it's a bad pick and let the multiplier suppress it.
   If it still dominates after a few tagged verdicts, the principled fix is
   `SMALL_CATEGORY_MAX` 5→4 in `outfit_history.py`. NB: the first #62 run *liked*
   the sandal in athleisure — keep the experiment scoped to Elevated/dressy.
8. **Spot-check inferred warmth values in the catalog UI** — open a handful of
   items and correct any rating that looks off (corrections stick; backfill never
   overwrites non-null). The prompt reasons over these numbers daily (#18).
9. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — tune trip
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
