# TODO

Working notes for picking up wardrobe-ai after a break. The source of truth for
tracked work is **GitHub Issues** + the **Projects board**; this file is the
scratchpad — half-formed ideas, where I left off, and links to the real artifacts.

> If something here matures past "scratch", promote it to a GitHub Issue and
> delete the line.

---

## Where I left off

**Last session (2026-06-02):** Diversity work scoped.

- **Daily-email "no-recommendation" hedge bug fixed** ([PR #14](https://github.com/JiamanBettyWu/wardrobe-ai/pull/14)). When Claude returned the skip-mode reasoning text **and** non-empty item_ids, the email template showed both the "no recommendation" message and outfit photos. Added a defensive `_is_skip()` check at hydration in [`recommend.py`](backend/services/recommend.py) and tightened the prompt to forbid the mixed shape.
- **Outfit-diversity problem scoped into issues.** After noticing repeated daily-email picks (same outfits 3 days running), traced the root cause to prompt anchoring — wardrobe sent in stable order, Claude gravitates to the top. Designed a recency-decay weighted sampler and filed [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) (the real work) plus three conditional follow-ups ([#16](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16), [#17](https://github.com/JiamanBettyWu/wardrobe-ai/issues/17), [#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18)) for tripwires we may or may not actually hit.

**Active work: [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15)** — recency-decay sampler. V1 ships **without** weather pre-filtering; soft weather scoring is parked in [#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) for when we hit deep winter/summer and the pool genuinely needs trimming.

**Next time I sit down, pick one:**
1. **[#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15)** — outfit-diversity sampler (active; designed, not yet built)
2. **[#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)** — replace the purchase stub with real SerpAPI Google Shopping results
3. **[#9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)** — fix the weather-window crash so trips >5 days out don't 502
4. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — prompt tuning after a real trip (best done *after* actually using the planner for Oaxaca)
5. **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)** — speed up the planner (parallelize weather + catalog, trim payload)

---

## Open issues (tracked)

- [#1 Catalog displays by categories](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
- [#2 Speed up trip planner generation](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)
- [#4 Tune trip planner prompts based on real-trip usage](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)
- [#5 Prepare repo for public release (portfolio)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)
- [#9 Trip planner crashes for trips starting >5 days out (OWM forecast window)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)
- [#10 Real purchase search: replace stub with SerpAPI Google Shopping](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)
- [#13 Align local Python version with Render (3.11)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13)
- **[#15 Outfit diversity: per-item recency decay + weighted sampling](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15)** ← active
- [#16 Diversity follow-up: category floors if sampled pool is incoherent](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16) (conditional on #15)
- [#17 Diversity follow-up: dedup exact outfit-set repeats](https://github.com/JiamanBettyWu/wardrobe-ai/issues/17) (conditional on #15)
- [#18 Diversity follow-up: soft weather scoring as a sampling multiplier](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) (deferred until winter/summer)

Closed since last sync: [#3](https://github.com/JiamanBettyWu/wardrobe-ai/issues/3), [#6](https://github.com/JiamanBettyWu/wardrobe-ai/issues/6), [#11](https://github.com/JiamanBettyWu/wardrobe-ai/pull/11) (env consolidation), [#12](https://github.com/JiamanBettyWu/wardrobe-ai/pull/12) (Render schema-order fix), [#14](https://github.com/JiamanBettyWu/wardrobe-ai/pull/14) (elevated-mode hedge).

See the [Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/projects)
for status (Todo / In Progress / Done).

---

## Scratch — not yet promoted

Things I might do but aren't worth an issue yet. Move up to Issues when they
firm up.

- ~~Consider an `outfits` history table~~ — promoted: lands as part of [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) (`outfit_history` table for recency tracking, which also unlocks "what did I wear last Tuesday").
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
