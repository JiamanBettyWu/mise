# TODO

Working notes for picking up wardrobe-ai after a break. The source of truth for
tracked work is **GitHub Issues** + the **Projects board**; this file is the
scratchpad — half-formed ideas, where I left off, and links to the real artifacts.

> If something here matures past "scratch", promote it to a GitHub Issue and
> delete the line.

---

## Where I left off

**Last session (2026-06-09 → 06-10):** Feedback-loop + warmth scoped end-to-end; sandals incident root-caused and fixed; email feedback, category-aware recency, the warmth attribute, and warmth-in-prompt + extremes gate all shipped — every structural piece of the plan is now live (only the data-dependent #42 and optional #41/#16 remain). Plus test infrastructure: pytest migration + CI on every PR.

- **Warmth in prompt + extremes gate shipped** ([#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) → [PR #56](https://github.com/JiamanBettyWu/wardrobe-ai/pull/56)) — last structural piece of the feedback-loop design (D′). `OUTFIT_SYSTEM_PROMPT` now explains the warmth 1–5 rating and asks for combined *layered* warmth to suit the day's high/low. New `services/weather_gate.py` runs before sampling: low ≥ 25°C drops warmth-5 items; high ≤ −5°C drops warmth-1 **footwear only** (tops/bottoms can layer; a wrongly gated base layer is unrecoverable). NULL warmth never gated; drops logged with item names. In SF the gate is a no-op most days — the prompt line is the part doing daily work. 8 pure tests in `tests/test_weather_gate.py`.

- **Test suite moved to pytest** ([#52](https://github.com/JiamanBettyWu/wardrobe-ai/issues/52) → [PR #54](https://github.com/JiamanBettyWu/wardrobe-ai/pull/54)). Five root-level scripts (incl. the gitignored `test_graph.py`, now committed with real graph-shape assertions) became `backend/tests/` — one command: `uv run pytest` (offline, 33 tests); `RUN_E2E=1` adds the live pipeline with dynamic in-window dates. `conftest.py` owns sys.path + .env loading; monkeypatch replaced the leaky global-poking. CI followed same session ([#53](https://github.com/JiamanBettyWu/wardrobe-ai/issues/53) → [PR #55](https://github.com/JiamanBettyWu/wardrobe-ai/pull/55)): the offline suite runs on every PR + push to main, pinned to **Python 3.11 (= Render)** so the 3.14 lazy-annotation gotcha is caught on the PR instead of on deploy (defangs most of [#13](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13)). No secrets needed; first runs green in ~20s.
- **Warmth attribute shipped** ([#40](https://github.com/JiamanBettyWu/wardrobe-ai/issues/40) → [PR #51](https://github.com/JiamanBettyWu/wardrobe-ai/pull/51)). `clothing_items.warmth` (1–5, nullable), inferred at tagging via an anchored rubric (`WARMTH_SCALE` shared between the vision prompt and `jobs/backfill_warmth.py` so they can't drift), editable in the item modal, and included in `WARDROBE_FIELDS`. Backfill ran 2026-06-10: **64/64 items rated** (distribution 1×20 / 2×27 / 3×10 / 4×5 / 5×1 — summer-heavy catalog, as expected in June). Backfill is fill-nulls-only, so hand corrections stick; safe to re-run. `season` officially demoted to display metadata. Unblocked [#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18), which shipped the same session ([PR #56](https://github.com/JiamanBettyWu/wardrobe-ai/pull/56)).
- **Category-aware recency shipped** ([#44](https://github.com/JiamanBettyWu/wardrobe-ai/issues/44) → [PR #50](https://github.com/JiamanBettyWu/wardrobe-ai/pull/50)). Items in categories with ≤5 *available* items get no recency weighting (weight 1.0, same as never-recommended) — rotation pressure only makes sense when substitutes exist. Live catalog: footwear (5) and dresses (3) exempt; tops/bottoms/outerwear still weighted. Pure `_sampling_weights` helper; category via `services/categories.py`. Sandals fix 1-of-3 done; [#16](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16) (category floors) covers the remaining eviction mechanism.

- **Recommendation-quality scoping session** → decision record in [docs/feedback-loop-design.md](docs/feedback-loop-design.md), filed as issues [#39](https://github.com/JiamanBettyWu/wardrobe-ai/issues/39) (email-first feedback via signed-token links), [#41](https://github.com/JiamanBettyWu/wardrobe-ai/issues/41) (web thumbs), [#40](https://github.com/JiamanBettyWu/wardrobe-ai/issues/40) (warmth 1–5, metadata-only backfill; `season` demoted to display-only), [#42](https://github.com/JiamanBettyWu/wardrobe-ai/issues/42) (feedback → sampling multiplier, smoothed + clamped [0.6, 1.4]), [#44](https://github.com/JiamanBettyWu/wardrobe-ai/issues/44) (no recency weighting for categories ≤5 items). [#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) rewritten in place (warmth in prompt + extremes gate **replaces** the soft weather multiplier; blocked on #40). [#16](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16)'s trigger condition officially fired. Organizing principle: *stochastic weights for preferences, deterministic logic for physics.*
- **Sandals fix shipped** ([#43](https://github.com/JiamanBettyWu/wardrobe-ai/issues/43) → [PR #45](https://github.com/JiamanBettyWu/wardrobe-ai/pull/45)). Root cause: the outfit prompt *mandated* shoes per outfit while the skip convention was all-or-nothing per mode — and the catalog has exactly one elevated-capable pair among 5 footwear items, which the 0.7 sample drops ~30% of days. Prompt may now omit a slot and note the gap in `reasoning`. Verify in the next few daily emails.
- **Email feedback shipped** ([#39](https://github.com/JiamanBettyWu/wardrobe-ai/issues/39) → [PR #49](https://github.com/JiamanBettyWu/wardrobe-ai/pull/49)). Daily-email outfit cards now carry 👍/👎 links; the verdict lands on the `outfit_history` row via `GET /feedback/{token}` (HMAC-signed token IS the auth — no password header from an email client). Re-click overwrites, latest wins. Job signs in-process on the Actions runner; Render verifies; `FEEDBACK_SECRET` must match in `.env`/Render/Actions (documented in AGENTS.md). Both deploy steps done and verified (migration columns exist; live endpoint accepts a probe token signed with the local secret). Unblocks [#41](https://github.com/JiamanBettyWu/wardrobe-ai/issues/41) (web thumbs) and [#42](https://github.com/JiamanBettyWu/wardrobe-ai/issues/42) (feedback → sampling). New offline tests in `tests/test_feedback_token.py` (run via `uv run pytest`).
- **Output validation shipped** ([#46](https://github.com/JiamanBettyWu/wardrobe-ai/issues/46) → [PR #47](https://github.com/JiamanBettyWu/wardrobe-ai/pull/47) prompt rule + [PR #48](https://github.com/JiamanBettyWu/wardrobe-ai/pull/48) enforcement), after a two-pants-in-one-mode incident. Pure `validate_outfit` (≤1 bottoms, ≤1 footwear, no dupe/unknown ids; no minimums — slot omission stays valid) + up to 2 *targeted* repair calls quoting violations back (informed repair, not blind retry) + deterministic `drop_extras` fallback, so the daily email can never fail on a structural slip. New shared `TYPE_CATEGORIES` map in `services/categories.py` (the groundwork [#44](https://github.com/JiamanBettyWu/wardrobe-ai/issues/44) needs). Validation triggers log warnings — grep the Actions logs to see the failure rate. New offline tests in `tests/test_validation.py` (run via `uv run pytest`).

**Previous session (2026-06-08):** Weather-window crash fixed.

- **Forecast coverage + inferred climate** ([#9](https://github.com/JiamanBettyWu/wardrobe-ai/issues/9) → [PR #38](https://github.com/JiamanBettyWu/wardrobe-ai/pull/38)). Trip planner now distinguishes `full_forecast`, `partial_forecast`, and `inferred_climate` instead of crashing when OWM `/forecast` has no overlapping dates. Added a LangGraph `infer_weather_if_needed` node that asks Claude for a trip-level climate estimate only when the live forecast is partial/missing; UI labels Forecast vs Partial forecast + climate estimate vs Climate estimate. Also hardened Claude JSON parser diagnostics while keeping 502 details generic client-side. Manually verified forecasted, partial, and inferred trip cases.

**Previous session (2026-06-05):** Four UI changes shipped.

- **Laundry filter + symmetric bulk reset** ([#36](https://github.com/JiamanBettyWu/wardrobe-ai/issues/36) → [PR #37](https://github.com/JiamanBettyWu/wardrobe-ai/pull/37)). Fixed an asymmetry: packed items had a management view (Travel mode); laundry didn't. Catalog now uses one mutually-exclusive `view` state (`all`/`packed`/`laundry`); "In laundry" mirrors Travel mode. Each active view gets a contextual ghost bulk reset (Unpack all / Clear laundry) behind a `confirm`, via `Promise.all` of PATCHes. Per-item undo is the existing card chip. (Detour: iCloud eviction had nuked `frontend/node_modules` + `backend/.venv` — rebuilt via `npm ci` / `uv sync`; see the resolved note below.)
- **Glass toggle chips on catalog cards** ([#34](https://github.com/JiamanBettyWu/wardrobe-ai/issues/34) → [PR #35](https://github.com/JiamanBettyWu/wardrobe-ai/pull/35)). Replaced the native "In laundry" / "Packed" checkboxes — the one un-glassy OS control on the card — with `.chip` pills. Off = ghost pill (still pressable, distinct from metadata); laundry-on = soft muted fill (reuses `--unavailable` dimming); packed-on = strong ink fill. Two fill weights on purpose, no new colors. Rendered as `<button aria-pressed>`. Approved mockup committed at [docs/design/laundry-packed-chips.png](docs/design/laundry-packed-chips.png).
- **Clear action on Today's Outfit** ([#32](https://github.com/JiamanBettyWu/wardrobe-ai/issues/32) → [PR #33](https://github.com/JiamanBettyWu/wardrobe-ai/pull/33)). Ghost "Clear" button next to Generate (shown only when there's notes/results), mirroring the trip planner's "Plan another trip" reset. Wipes notes/data/error but **preserves travel mode** (standing preference, not part of one ask). Promoted the ghost style to a reusable `.ghost` modifier.
- **Typography → runtime font tokens** ([PR #31](https://github.com/JiamanBettyWu/wardrobe-ai/pull/31), no tracked issue — ad-hoc). Moved CSS off hardcoded `'EB Garamond'` onto `--font-heading/body/mono` set by a new `FontProvider` ([frontend/src/fonts.jsx](frontend/src/fonts.jsx)). Active pairing is **Cormorant Garamond + DM Sans**; re-theme the whole app via `ACTIVE_COMBO`. Dev-only `<FontPicker>` previews 5 combos live (gated by `import.meta.env.DEV`, stripped from prod). Modal close button stays hardcoded `system-ui` (glyph-safety).

**Two sessions back (2026-06-04):** Two redesign follow-ups shipped back-to-back.

- **Persist Today's outfit results** ([#26](https://github.com/JiamanBettyWu/wardrobe-ai/issues/26) → [PR #28](https://github.com/JiamanBettyWu/wardrobe-ai/pull/28)). Mirrors the Trip persistence pattern: `today_state` in `localStorage` survives navigation, with `generatedOn` gating expiry so yesterday's pick is dropped on hydrate. Geolocation is intentionally not persisted (cheap to re-request, stale coords would mislabel "your location").
- **Destination autocomplete** ([#27](https://github.com/JiamanBettyWu/wardrobe-ai/issues/27) → [PR #29](https://github.com/JiamanBettyWu/wardrobe-ai/pull/29)). New `GET /geo/search` route proxies OWM `/geo/1.0/direct` server-side. `TripPlan` destination is now a debounced combobox with ArrowUp/Down + Enter + Escape nav. Selected coords thread through `TripPlanRequest` → `PackingState` → `get_weather_node`, skipping the redundant backend geocode. Free-text fallback still works.

**Earlier 2026-06-04:** Glass design system landed across the whole frontend (cards, modal, nav, buttons, inputs, outfit tiles, trip results) and is documented in [DESIGN.md](DESIGN.md) with a dated decisions log. CLAUDE.md points to it so future UI work stays coherent.

**✅ Resolved (was: run Disk Utility → First Aid):** No disk check needed — the disk was never the problem. The 2026-06-05 NUL-byte "corruption" in `frontend/node_modules` + `backend/.venv` was **iCloud eviction**, not filesystem damage. The repo lived on `~/Desktop` (iCloud "Desktop & Documents" + "Optimize Mac Storage" on), so file *contents* were evicted to the cloud and stalled on-demand re-downloads read as NUL bytes / `total 0` blocks. `verifyVolume /` came back clean and SMART was healthy because the hardware was always fine. **Fix applied:** moved this repo (and all active projects) to `~/dev`, outside iCloud; migration verified complete 2026-06-08. Rule going forward: never keep repos / `node_modules` / `.venv` in Desktop or Documents with iCloud sync on. See LEARNINGS for the full "hanging import → iCloud eviction" trail.

**Next time I sit down, pick one:**
1. **Click a thumb in the next daily email** — first end-to-end run of #39 with real data: links render → confirmation page → row gets `feedback`. (Deploy fully verified 2026-06-10; this is just the human-in-the-loop check.)
2. **Spot-check inferred warmth values in the catalog UI** — open a handful of items and correct any rating that looks off (corrections stick; the backfill never overwrites non-null values). The prompt now reasons over these numbers daily (#18 shipped), so a bad rating has real effect.
3. **Check the daily emails for the #43 + #44 fixes** — Elevated should now either include the flats (no longer recency-suppressed) or omit shoes with a note, never sport sandals.
4. **Live with the redesign + new fonts + combobox for a couple days** and note anything that grates — file follow-ups if so. (Cormorant is easy to swap if it doesn't wear well: change `ACTIVE_COMBO` or run `npm run dev` for the live picker.)
5. **Watch 3 days of daily emails** to validate [#15](https://github.com/JiamanBettyWu/wardrobe-ai/issues/15) actually fixed the repetition problem.
6. **[#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)** — replace the purchase stub with real SerpAPI Google Shopping results
7. **[#4](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)** — prompt tuning after a real trip (best done *after* actually using the planner for Oaxaca)
8. **[#2](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)** — speed up the planner (parallelize weather + catalog, trim payload)
9. **[#24](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)** — multi-item tagging (B-lite) + bbox feasibility experiment

---

## Open issues (tracked)

- [#1 Catalog displays by categories](https://github.com/JiamanBettyWu/wardrobe-ai/issues/1)
- [#2 Speed up trip planner generation](https://github.com/JiamanBettyWu/wardrobe-ai/issues/2)
- [#4 Tune trip planner prompts based on real-trip usage](https://github.com/JiamanBettyWu/wardrobe-ai/issues/4)
- [#5 Prepare repo for public release (portfolio)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/5)
- [#10 Real purchase search: replace stub with SerpAPI Google Shopping](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10)
- [#13 Align local Python version with Render (3.11)](https://github.com/JiamanBettyWu/wardrobe-ai/issues/13) (largely defanged 2026-06-10 — CI now runs the suite on 3.11 per [PR #55](https://github.com/JiamanBettyWu/wardrobe-ai/pull/55); remaining value is local-dev parity)
- [#16 Diversity follow-up: category floors if sampled pool is incoherent](https://github.com/JiamanBettyWu/wardrobe-ai/issues/16) (**trigger fired** — sandals incident; the last unshipped sandals mechanism now that #43 + #44 landed: the 0.7 sample can still evict a small category wholesale)
- [#17 Diversity follow-up: dedup exact outfit-set repeats](https://github.com/JiamanBettyWu/wardrobe-ai/issues/17) (conditional — only if exact combos still repeat)
- [#24 Multi-item tagging from a single photo (B-lite) + Claude bbox feasibility check](https://github.com/JiamanBettyWu/wardrobe-ai/issues/24)
- [#30 Eval harness scaffold for trip_planner LangGraph pipeline](https://github.com/JiamanBettyWu/wardrobe-ai/issues/30) (design firms up after [#10](https://github.com/JiamanBettyWu/wardrobe-ai/issues/10))
- [#41 Feedback loop: web thumbs on TodayOutfit](https://github.com/JiamanBettyWu/wardrobe-ai/issues/41) (unblocked — #39 shipped; reuse `services/feedback_token.py` row update or an authed POST)
- [#42 Feedback factor in sampling: smoothed like-rate → clamped multiplier](https://github.com/JiamanBettyWu/wardrobe-ai/issues/42) (unblocked — #39 shipped; wants a couple weeks of verdicts first)

The feedback-loop/warmth issue cluster (#39–#44, #18, #16) is mapped with rationale in [docs/feedback-loop-design.md](docs/feedback-loop-design.md).

Closed last session: [#43](https://github.com/JiamanBettyWu/wardrobe-ai/issues/43) (prompt may omit a slot instead of forcing off-mode items → [PR #45](https://github.com/JiamanBettyWu/wardrobe-ai/pull/45)), [#46](https://github.com/JiamanBettyWu/wardrobe-ai/issues/46) (output validation: prompt rule → [PR #47](https://github.com/JiamanBettyWu/wardrobe-ai/pull/47), repair + fallback → [PR #48](https://github.com/JiamanBettyWu/wardrobe-ai/pull/48)), [#39](https://github.com/JiamanBettyWu/wardrobe-ai/issues/39) (email 👍/👎 via signed-token links → [PR #49](https://github.com/JiamanBettyWu/wardrobe-ai/pull/49); deploy verified), [#44](https://github.com/JiamanBettyWu/wardrobe-ai/issues/44) (small categories skip recency weighting → [PR #50](https://github.com/JiamanBettyWu/wardrobe-ai/pull/50)), [#40](https://github.com/JiamanBettyWu/wardrobe-ai/issues/40) (warmth 1–5: tagging + backfill + UI → [PR #51](https://github.com/JiamanBettyWu/wardrobe-ai/pull/51); all 64 items rated), [#52](https://github.com/JiamanBettyWu/wardrobe-ai/issues/52) (pytest migration → [PR #54](https://github.com/JiamanBettyWu/wardrobe-ai/pull/54)), [#53](https://github.com/JiamanBettyWu/wardrobe-ai/issues/53) (CI: offline suite on every PR, pinned to Render's 3.11 → [PR #55](https://github.com/JiamanBettyWu/wardrobe-ai/pull/55)), [#18](https://github.com/JiamanBettyWu/wardrobe-ai/issues/18) (warmth in prompt + deterministic extremes gate → [PR #56](https://github.com/JiamanBettyWu/wardrobe-ai/pull/56)).

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
