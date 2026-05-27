# TODO

Working notes for picking up wardrobe-ai after a break. The source of truth for
tracked work is **GitHub Issues** + the **Projects board**; this file is the
scratchpad — half-formed ideas, where I left off, and links to the real artifacts.

> If something here matures past "scratch", promote it to a GitHub Issue and
> delete the line.

---

## Where I left off

**Last session (2026-05-26):** V1 LangGraph trip planner is working end-to-end
(weather → catalog → reason_and_select → generate_output). Daily outfit email
cron is healthy after the `tzdata` fix. Set up project management — opened
issues #2/#3/#4 and created this file.

**Next time I sit down, pick one:**
1. **#3** — `search_purchases` + `check_gaps` conditional edge (completes V1 spec)
2. **#2** — speed up the planner (parallel nodes, trim payload)
3. **#4** — prompt tuning after a real trip

---

## Open issues (tracked)

- [#1 Catalog displays by categories](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
- [#2 Speed up trip planner generation](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)
- [#3 Complete LangGraph V1: search_purchases + check_gaps](https://github.com/JiamanBettyWu/wardrobe-ai/issues/3)
- [#4 Tune trip planner prompts based on real-trip usage](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)
- [#5 Prepare repo for public release (portfolio)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)

See the [Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/projects)
for status (Todo / In Progress / Done).

---

## Scratch — not yet promoted

Things I might do but aren't worth an issue yet. Move up to Issues when they
firm up.

- Remove `[debug]` print from `jobs/daily_outfit.py` once the cron has been
  trusted for ~2 weeks.
- Add `backend/test_graph.py` to `.gitignore` (currently an untracked throwaway).
- Consider an `outfits` history table — would unlock "what did I wear last
  Tuesday" and feedback signal for reranking.
- V2 ideas (deferred from trip planner spec): calendar integration, day-by-day
  outfits, persisted trips, multi-destination.

---

## Conventions

- **Issues** for anything that needs to survive a session-context wipe or
  benefits from discussion in the PR.
- **TODO.md (this file)** for the freshest "where am I" pointer and quick
  scratch.
- **PRs close issues** with `Closes #N` in the description so the board
  auto-moves cards to Done.
- **Labels**: `enhancement`, `bug`, `tech-debt`, `prompt-tuning`, `langgraph`.
- **Milestones**: `V1` (current), `V2`, `Public launch`.
