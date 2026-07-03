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

**As of 2026-07-02 (evening):** the bbox experiment (#96, PR #97) ran on 5 real
photos and came back **feasible** — B-full implementation is filed as
**[#100](https://github.com/JiamanBettyWu/wardrobe-ai/issues/100)** — and #24's
multi-item flow is verified live on the phone (earlier today: B-lite #24/PR #94,
empty-tagging parity PR #98, formatter sweep #90/PR #99). **⚠️ Manual follow-up
still open — rotate the SerpAPI + OpenWeatherMap keys** (they appeared in logs
before #89); full detail lives in [SESSIONS.md](SESSIONS.md).

---

## Next time I sit down, pick one

1. **Rotate the SerpAPI + OpenWeatherMap keys** (do this first — see Current
   state). Then optionally [#86](https://github.com/JiamanBettyWu/wardrobe-ai/issues/86)
   (MCP stretch: Streamable HTTP transport + `langchain-mcp-adapters` into a
   LangGraph node — the part most transferable to the work MCP project).
2. **Let the weekly inference job (#62) accumulate, and curate it.** The Sunday
   cron (`20 1 * * 1`) re-derives inferred prefs from the whole verdict history
   each week — keep clicking/tagging thumbs; volume is the whole game. Each week
   glance at Profile → *Learned from your feedback*: dismiss any statement that
   doesn't ring true (that **tombstones** it — the job won't re-emit it), or
   "Edit & own" to promote it to a hard pref. The "reviewed N days ago"
   heartbeat flags if the cron ever stops.
3. **Confirm inferred prefs actually shift generation** — they ride the prompt as
   *soft* "Learned preferences", so watch whether athleisure picks drift toward
   open footwear over the next several days. Lever if too weak/strong: the
   "Learned preferences" bullet in `claude.py`.
4. **Check the first real-event morning for #64's events path** — the empty-day
   path is verified live; on a morning with calendar events the Actions log
   should show `calendar: N event(s) → modes: …` and the email should carry the
   📅 explanation line.
5. **The sport-sandal experiment** (decided 2026-06-12): the footwear floor
   works; the model just keeps *choosing* the sandal. Plan: tag the sandal with a
   `specific_items` 👎 when it's a bad pick and let the multiplier suppress it.
   If it still dominates after a few tagged verdicts, the principled fix is
   `SMALL_CATEGORY_MAX` 5→4 in `outfit_history.py`. NB: the first #62 run *liked*
   the sandal in athleisure — keep the experiment scoped to Elevated/dressy.
6. **Spot-check inferred warmth values in the catalog UI** — open a handful of
   items and correct any rating that looks off (corrections stick; backfill never
   overwrites non-null). The prompt reasons over these numbers daily (#18).
7. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — tune trip
   planner prompts after a real trip (best done *after* actually using the
   planner for Oaxaca).
8. **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)** — speed up the
   planner (parallelize weather + catalog, trim payload).
9. **[#100](https://github.com/JiamanBettyWu/wardrobe-ai/issues/100) — B-full:
   cropped per-item thumbnails** in the `upload-multi` flow (bbox in the
   multi-tagging prompt, pre-resize below the vision API limits, ~10%-padded
   crops). Mind the flagged wrinkle: per-item crop URLs break PR #94's
   `photo_url` delete ref-counting.
   [#95](https://github.com/JiamanBettyWu/wardrobe-ai/issues/95) (Travel-mode
   checkboxes → `.switch`) is a quick one alongside.

Other tracked-but-not-urgent: [#1](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
(catalog by categories), [#5](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)
(prepare repo for public release), [#13](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13)
(local Python → 3.11 parity; largely defanged by CI),
[#30](https://github.com/JiamanBettyWu/wardrobe-ai/issues/30) (eval harness for
the trip-planner LangGraph). See the
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
