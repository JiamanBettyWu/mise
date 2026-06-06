# TODO

Working notes for picking up wardrobe-ai after a break. The source of truth for
tracked work is **GitHub Issues** + the **Projects board**; this file is the
scratchpad — half-formed ideas, where I left off, and links to the real artifacts.

> If something here matures past "scratch", promote it to a GitHub Issue and
> delete the line.

---

## Where I left off

**Last session (2026-06-05):** Four UI changes shipped.

- **Laundry filter + symmetric bulk reset** ([#36](https://github.com/JiamanBettyWu/wardrobe-ai/issues/36) → [PR #37](https://github.com/JiamanBettyWu/wardrobe-ai/pull/37)). Fixed an asymmetry: packed items had a management view (Travel mode); laundry didn't. Catalog now uses one mutually-exclusive `view` state (`all`/`packed`/`laundry`); "In laundry" mirrors Travel mode. Each active view gets a contextual ghost bulk reset (Unpack all / Clear laundry) behind a `confirm`, via `Promise.all` of PATCHes. Per-item undo is the existing card chip. (Detour: filesystem corruption had nuked `frontend/node_modules` + `backend/.venv` — rebuilt via `npm ci` / `uv sync`; see disk note below.)
- **Glass toggle chips on catalog cards** ([#34](https://github.com/JiamanBettyWu/wardrobe-ai/issues/34) → [PR #35](https://github.com/JiamanBettyWu/wardrobe-ai/pull/35)). Replaced the native "In laundry" / "Packed" checkboxes — the one un-glassy OS control on the card — with `.chip` pills. Off = ghost pill (still pressable, distinct from metadata); laundry-on = soft muted fill (reuses `--unavailable` dimming); packed-on = strong ink fill. Two fill weights on purpose, no new colors. Rendered as `<button aria-pressed>`. Approved mockup committed at [docs/design/laundry-packed-chips.png](docs/design/laundry-packed-chips.png).
- **Clear action on Today's Outfit** ([#32](https://github.com/JiamanBettyWu/wardrobe-ai/issues/32) → [PR #33](https://github.com/JiamanBettyWu/wardrobe-ai/pull/33)). Ghost "Clear" button next to Generate (shown only when there's notes/results), mirroring the trip planner's "Plan another trip" reset. Wipes notes/data/error but **preserves travel mode** (standing preference, not part of one ask). Promoted the ghost style to a reusable `.ghost` modifier.
- **Typography → runtime font tokens** ([PR #31](https://github.com/JiamanBettyWu/wardrobe-ai/pull/31), no tracked issue — ad-hoc). Moved CSS off hardcoded `'EB Garamond'` onto `--font-heading/body/mono` set by a new `FontProvider` ([frontend/src/fonts.jsx](frontend/src/fonts.jsx)). Active pairing is **Cormorant Garamond + DM Sans**; re-theme the whole app via `ACTIVE_COMBO`. Dev-only `<FontPicker>` previews 5 combos live (gated by `import.meta.env.DEV`, stripped from prod). Modal close button stays hardcoded `system-ui` (glyph-safety).

**Previous session (2026-06-04):** Two redesign follow-ups shipped back-to-back.

- **Persist Today's outfit results** ([#26](https://github.com/JiamanBettyWu/wardrobe-ai/issues/26) → [PR #28](https://github.com/JiamanBettyWu/wardrobe-ai/pull/28)). Mirrors the Trip persistence pattern: `today_state` in `localStorage` survives navigation, with `generatedOn` gating expiry so yesterday's pick is dropped on hydrate. Geolocation is intentionally not persisted (cheap to re-request, stale coords would mislabel "your location").
- **Destination autocomplete** ([#27](https://github.com/JiamanBettyWu/wardrobe-ai/issues/27) → [PR #29](https://github.com/JiamanBettyWu/wardrobe-ai/pull/29)). New `GET /geo/search` route proxies OWM `/geo/1.0/direct` server-side. `TripPlan` destination is now a debounced combobox with ArrowUp/Down + Enter + Escape nav. Selected coords thread through `TripPlanRequest` → `PackingState` → `get_weather_node`, skipping the redundant backend geocode. Free-text fallback still works.

**Two sessions back (2026-06-04 earlier):** Glass design system landed across the whole frontend (cards, modal, nav, buttons, inputs, outfit tiles, trip results) and is documented in [DESIGN.md](DESIGN.md) with a dated decisions log. CLAUDE.md points to it so future UI work stays coherent.

**⚠️ Unfinished follow-up:** run **Disk Utility → First Aid** on the Mac. On 2026-06-05 two dirs (`frontend/node_modules`, `backend/.venv`) had NUL-corrupted files from a past filesystem event — both rebuilt, SMART reports healthy, but the FS metadata should be verified (boot volume needs Recovery mode). See LEARNINGS for the "hanging import = corrupted site-packages" diagnosis.

**Next time I sit down, pick one:**
1. **Live with the redesign + new fonts + combobox for a couple days** and note anything that grates — file follow-ups if so. (Cormorant is easy to swap if it doesn't wear well: change `ACTIVE_COMBO` or run `npm run dev` for the live picker.)
2. **Watch 3 days of daily emails** to validate [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) actually fixed the repetition problem.
3. **[#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)** — replace the purchase stub with real SerpAPI Google Shopping results
4. **[#9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9)** — fix the weather-window crash so trips >5 days out don't 502
5. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — prompt tuning after a real trip (best done *after* actually using the planner for Oaxaca)
6. **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)** — speed up the planner (parallelize weather + catalog, trim payload)
7. **[#24](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)** — multi-item tagging (B-lite) + bbox feasibility experiment

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
- [#30 Eval harness scaffold for trip_planner LangGraph pipeline](https://github.com/JiamanBettyWu/wardrobe-ai/issues/30) (design firms up after [#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10))

Closed last session: [#36](https://github.com/JiamanBettyWu/wardrobe-ai/issues/36) (laundry filter + bulk reset → [PR #37](https://github.com/JiamanBettyWu/wardrobe-ai/pull/37)); [#34](https://github.com/JiamanBettyWu/wardrobe-ai/issues/34) (glass toggle chips → [PR #35](https://github.com/JiamanBettyWu/wardrobe-ai/pull/35)); [#32](https://github.com/JiamanBettyWu/wardrobe-ai/issues/32) (Today's Outfit Clear action → [PR #33](https://github.com/JiamanBettyWu/wardrobe-ai/pull/33)); font-tokens typography refactor → [PR #31](https://github.com/JiamanBettyWu/wardrobe-ai/pull/31) (no issue — ad-hoc).

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
