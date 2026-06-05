# TODO

Working notes for picking up wardrobe-ai after a break. The source of truth for
tracked work is **GitHub Issues** + the **Projects board**; this file is the
scratchpad — half-formed ideas, where I left off, and links to the real artifacts.

> If something here matures past "scratch", promote it to a GitHub Issue and
> delete the line.

---

## Where I left off

**Last session (2026-06-04):** Glass design system landed across the whole frontend (cards, modal, nav, buttons, inputs, outfit tiles, trip results) and is documented in [DESIGN.md](DESIGN.md) with a dated decisions log. CLAUDE.md points to it so future UI work stays coherent. Filed two follow-ups while using the redesigned app: [#26](https://github.com/JiamanBettyWu/wardrobe-ai/issues/26) (persist Today's outfit results like Trip does) and [#27](https://github.com/JiamanBettyWu/wardrobe-ai/issues/27) (city autocomplete on the Trip destination input via OWM geocoding).

**Previous session (2026-06-03):** Quick login-error UX fix shipped ([#21](https://github.com/JiamanBettyWu/wardrobe-ai/issues/21) → [PR #23](https://github.com/JiamanBettyWu/wardrobe-ai/pull/23)). Unlock screen now branches on the thrown error's status prefix: 401 → "Wrong password.", 500 → "Server misconfigured.", anything else → "Could not reach the server." No more debugging confusion when the backend is just down.

**Two sessions back (2026-06-02):** Two PRs shipped.

- **Outfit diversity sampler** ([#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) → [PR #19](https://github.com/JiamanBettyWu/wardrobe-ai/pull/19)). New `outfit_history` Supabase table tracks per-(date, mode) recommendations. `sample_wardrobe()` returns ~70% of items weighted by exponentially-decayed recency (`p ∝ 1/(1+s)`), then shuffles. Tunables (`HISTORY_WINDOW_DAYS=7`, `DAILY_DECAY=0.85`, `SAMPLE_FRACTION=0.7`) at the top of [`outfit_history.py`](backend/services/outfit_history.py). Real signal lands over the next few days of cron emails — eyeball whether outfits visibly vary.
- **Trip planner persistence** ([#20](https://github.com/JiamanBettyWu/wardrobe-ai/issues/20) → [PR #22](https://github.com/JiamanBettyWu/wardrobe-ai/pull/22)). Form + result now persist in `localStorage` across navigation/reload until either "Plan another trip" is clicked or the plan's `end_date` is past (silent expiry).

**Next time I sit down, pick one:**
1. **Live with the redesign for a couple days** and note anything that grates — file follow-ups if so.
2. **[#26](https://github.com/JiamanBettyWu/wardrobe-ai/issues/26)** — persist Today's outfit results across navigation (small, mirrors the Trip pattern)
3. **[#27](https://github.com/JiamanBettyWu/wardrobe-ai/issues/27)** — destination autocomplete via OWM geocoding (real travel-site feel)
4. **Watch 3 days of daily emails** to validate [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) actually fixed the repetition problem.
5. **[#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)** — replace the purchase stub with real SerpAPI Google Shopping results
6. **[#9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)** — fix the weather-window crash so trips >5 days out don't 502
7. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — prompt tuning after a real trip (best done *after* actually using the planner for Oaxaca)
8. **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)** — speed up the planner (parallelize weather + catalog, trim payload)
9. **[#24](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)** — multi-item tagging (B-lite) + bbox feasibility experiment

---

## Open issues (tracked)

- [#1 Catalog displays by categories](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
- [#2 Speed up trip planner generation](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)
- [#4 Tune trip planner prompts based on real-trip usage](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)
- [#5 Prepare repo for public release (portfolio)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)
- [#9 Trip planner crashes for trips starting >5 days out (OWM forecast window)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)
- [#10 Real purchase search: replace stub with SerpAPI Google Shopping](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)
- [#13 Align local Python version with Render (3.11)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13)
- [#16 Diversity follow-up: category floors if sampled pool is incoherent](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16) (conditional — only if #15 starves a category)
- [#17 Diversity follow-up: dedup exact outfit-set repeats](https://github.com/JiamanBettyWu/wardrobe-ai/issues/17) (conditional — only if exact combos still repeat)
- [#18 Diversity follow-up: soft weather scoring as a sampling multiplier](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) (deferred until winter/summer)
- [#24 Multi-item tagging from a single photo (B-lite) + Claude bbox feasibility check](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)
- [#26 Persist Today's outfit results across navigation](https://github.com/JiamanBettyWu/wardrobe-ai/issues/26)
- [#27 Autocomplete destinations in Trip planner](https://github.com/JiamanBettyWu/wardrobe-ai/issues/27)

Closed last session: [#21](https://github.com/JiamanBettyWu/wardrobe-ai/issues/21) (login error UX → [PR #23](https://github.com/JiamanBettyWu/wardrobe-ai/pull/23)).

See the [Projects board](https://github.com/JiamanBettyWu/wardrobe-ai/projects)
for status (Todo / In Progress / Done).

---

## Scratch — not yet promoted

Things I might do but aren't worth an issue yet. Move up to Issues when they
firm up.

- ~~Consider an `outfits` history table~~ — promoted: lands as part of [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) (`outfit_history` table for recency tracking, which also unlocks "what did I wear last Tuesday").
- V2 ideas (deferred from trip planner spec): calendar integration, day-by-day
  outfits, multi-destination.
- **Option A multi-photo upload** (select N photos, one item per photo) — sibling of [#24](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)'s B-lite path. File separately if pursued.

---

## Larger plans (not in the issue tracker yet)

Plans too big for a single issue. Each gets split into a sequence of
issues/PRs when we're ready to do the work.

- **[Multi-user support](docs/multi-user-plan.md)** — let 3-5 friends use their own wardrobes. Deferred until the "friend-ready" milestone (see doc for the gating checklist).

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
