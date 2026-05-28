# TODO

Working notes for picking up wardrobe-ai after a break. The source of truth for
tracked work is **GitHub Issues** + the **Projects board**; this file is the
scratchpad — half-formed ideas, where I left off, and links to the real artifacts.

> If something here matures past "scratch", promote it to a GitHub Issue and
> delete the line.

---

## Where I left off

**Last session (2026-05-27):** Two milestones closed.

- **Daily email cron fixed** ([#6](https://github.com/JiamanBettyWu/wardrobe-ai/issues/6) → [PR #7](https://github.com/JiamanBettyWu/wardrobe-ai/pull/7)). The exact-hour TZ guard was incompatible with GitHub Actions' 1–3h cron delays; replaced with a single early-morning cron (`20 8 * * *`) that always sends. The email had **never** sent on schedule before this fix.
- **LangGraph V1 functionally complete** ([#3](https://github.com/JiamanBettyWu/wardrobe-ai/issues/3) → [PR #8](https://github.com/JiamanBettyWu/wardrobe-ai/pull/8)). Added `search_purchases` node + `check_gaps` conditional edge — the trip-planner fork now exists and is verified end-to-end. Purchase results are still a **stub**; real search is [#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10).

Two new issues surfaced from that work: [#9 (weather window crash)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9) and [#10 (real SerpAPI search)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10).

**Next time I sit down, pick one:**
1. **[#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)** — replace the purchase stub with real SerpAPI Google Shopping results (the natural follow-up to #3; small, scoped, high visible payoff)
2. **[#9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)** — fix the weather-window crash so trips >5 days out don't 502 (real robustness gap)
3. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — prompt tuning after a real trip (best done *after* actually using the planner for Oaxaca)
4. **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)** — speed up the planner (parallelize weather + catalog, trim payload)

---

## Open issues (tracked)

- [#1 Catalog displays by categories](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
- [#2 Speed up trip planner generation](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)
- [#4 Tune trip planner prompts based on real-trip usage](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)
- [#5 Prepare repo for public release (portfolio)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)
- [#9 Trip planner crashes for trips starting >5 days out (OWM forecast window)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)
- [#10 Real purchase search: replace stub with SerpAPI Google Shopping](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)

Closed since last sync: [#3](https://github.com/JiamanBettyWu/wardrobe-ai/issues/3), [#6](https://github.com/JiamanBettyWu/wardrobe-ai/issues/6).

See the [Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/projects)
for status (Todo / In Progress / Done).

---

## Scratch — not yet promoted

Things I might do but aren't worth an issue yet. Move up to Issues when they
firm up.

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
- **Branch per issue**, named `feat/issue-N-...` or `fix/...`. PRs close issues
  with `Closes #N` in the description so the board auto-moves cards to Done.
- **Solo-merge gotcha**: skip the formal "Approve" step on your own PRs — GitHub
  blocks self-approval. Use the green **Merge pull request** button directly.
- **Labels**: `enhancement`, `bug`, `tech-debt`, `prompt-tuning`, `langgraph`.
- **Milestones**: `V1` (current), `V2`, `Public launch`.
