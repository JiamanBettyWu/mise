# The daily outfit recommendation algorithm

**As of 2026-06-12** (post #59 — recent thumbed outfits as prompt context —
post #60 — optional 👎 attribution de-noises the multiplier and the
avoid-list, and `outfit_history` records weather + notes at recommendation
time — and post #63 — the model proposes 3 candidates per mode and a
deterministic filter rejects 👎-attributed combinations — and post #64 —
the daily job's modes optionally come from today's calendar; the full
feedback-loop design of #39–#44 was implemented in PR #58 and earlier).
This is the *how it works* reference; the *why we chose it* decision record is
[feedback-loop-design.md](feedback-loop-design.md). When the two disagree, the
code wins: [`services/recommend.py`](../backend/services/recommend.py) is the
entry point, [`services/outfit_history.py`](../backend/services/outfit_history.py)
is where almost all the math lives.

Used by `POST /outfits/recommend` (web) and `jobs/daily_outfit.py` (the morning
email, GitHub Actions cron). Same code path; the job passes named modes
(Smart casual / Athleisure / Elevated), the web UI passes none.

Which modes the job passes is itself an input, not part of the pipeline:
with the optional `CALENDAR_ICS_URL` secret set, today's Google Calendar
events drive mode selection (#64, [`services/calendar.py`](../backend/services/calendar.py)) —
no events → Smart casual only, gym class → + Athleisure, dinner out → +
Elevated, any failure → all three. The event listing also rides in as `notes`,
so the generator sees *why* a mode fired and `outfit_history` records it (#60).
Unset → the hardcoded three modes, unchanged.

---

## The big picture

```
weather ──► catalog ──► extremes gate ──► weighted sample (70%) ──► category
            (available,   (#18, hard       w = recency × feedback     floors (#16)
             travel        drop)            (#15/#44)   (#42)            │
             filter)                                                     ▼
                                                                      shuffle
                                                                         │
            outfit_history ◄── log rows ◄── validate/repair ◄── Claude picks
            (feedback lands     (#39)        (#46)              outfits per mode
             here: email #39,                                   (#43: may omit
             web #41)                                            a slot)
```

The sampler does **not** pick the outfit. It picks the ~70% of the wardrobe
Claude gets to *see* — the model makes the actual choices. Every weight below
shifts probabilities of pool membership, nothing more. Think of it as
curating the rack before the stylist walks in, not dressing the mannequin.

## The organizing principle

> *Stochastic weights for preferences, deterministic logic for physics.*

- **Soft signals** (taste, rotation fatigue) → multiplicative sampling
  weights. Probabilistic, fine to get wrong on any single day.
- **Hard constraints** (it's 30°C; an outfit needs ≤1 pair of pants) →
  deterministic gates and validators. "Why wasn't the coat shown?" must have
  an exact answer.

The sampling weight is a **product of bounded factors** so each factor ships
and tunes independently:

```
w_i = recency_factor_i × feedback_mult_i        # weather is NOT a factor here
```

---

## Stage 1 — Extremes gate (deterministic)

[`services/weather_gate.py`](../backend/services/weather_gate.py). Drops only
clear absurdities, *before* sampling, so they can't displace useful items in
the pool or waste prompt tokens:

| Condition | Dropped |
|---|---|
| daily low ≥ 25°C | warmth-5 items (down coat in a heatwave) |
| daily high ≤ −5°C | warmth-1 **footwear only** (sandals in frost) |

Why footwear-only on the cold side: a warmth-1 tee on a 3°C day is the base
layer under the sweater — item-level weather scoring is *anti-correlated*
with usefulness for layering pieces. Footwear is the one category that can't
layer. Items with `warmth NULL` (bags, belts) are never gated. Drops are
logged by name. In SF this gate is a no-op almost every day — the prompt's
warmth guidance (Stage 5) is the part doing daily work.

## Stage 2 — Recency score (the anti-repetition force)

For each item, sum a decayed contribution from every appearance in
`outfit_history` over the last `HISTORY_WINDOW_DAYS = 7`:

```
s_i = Σ over appearances of  DAILY_DECAY ^ days_ago        # DAILY_DECAY = 0.85
```

It's a decayed **sum**, not an exponent-of-count: recommended yesterday *and*
3 days ago → `s = 0.85 + 0.61 = 1.46`. Each appearance is a voice that fades
~15%/day (≈4-day half-life).

Scores are **per-mode**: history rows are filtered to today's requested
modes, so heavy use in Smart casual doesn't suppress an item for Athleisure.
With multiple modes today, scores sum across them. (Web requests pass no
modes → recency sums across all history.)

The score becomes a factor via a reciprocal squash:

```
recency_factor = 1 / (1 + s)        # s=0 → 1.0;  recommended-today → 0.5
```

Never reaches 0 — the sampler's founding rule from #15 is *less likely,
never excluded*.

**Small-category exemption (#44, the sandals incident):** items in categories
with ≤ `SMALL_CATEGORY_MAX = 5` *available* items get `recency_factor = 1.0`
unconditionally. Rotation pressure only makes sense when substitutes exist;
"you wore the good flats yesterday" must not evict the only elevated-capable
pair. Counts are over the post-gate, post-travel-filter wardrobe — substitutes
that don't exist *today* don't count. Category comes from the static
`type → category` map in [`services/categories.py`](../backend/services/categories.py)
(the `type` field is a closed vocabulary, so no inference is needed).

## Stage 3 — Feedback multiplier (the taste force, #42)

Thumbs verdicts are **outfit-level** (one tap in the email or on TodayOutfit);
weights are item-level. So each verdict is treated as a *noisy label on every
item in the outfit*, aggregated with beta-Bernoulli smoothing — the same math
as smoothed CTR:

```
ups_i   = Σ thumbed-up outfits containing i,   each contributing 1/len(item_ids)
downs_i = Σ thumbed-down outfits containing i, same fractional weighting

score_i = (ups_i + 1) / (ups_i + downs_i + 2)      # Laplace prior = 0.5
mult_i  = 0.6 + 0.8 × score_i                      # affine map [0,1] → [0.6, 1.4]
```

Details that matter:

- **Fractional credit**: one tap distributes one unit of credit/blame across
  the outfit (a 4-item outfit gives each item ¼), instead of minting 4 units.
  The prior pseudo-counts (+1/+2) stay whole, so evidence accumulates ~3–4×
  slower than the prior — items are convicted or exonerated **by
  accumulation, never by a single verdict**. Worked example: one 👎 on a
  3-item outfit → `downs = ⅓` → `score = 3/7` → `mult ≈ 0.94` per item.
- **Unrated = exactly 1.0**: neutral score 0.5 maps to 1.0, so the feature is
  purely additive — behavior without feedback is unchanged.
- **Bounds are built into the formula**, not clamped after: 0.6 and 1.4 are
  asymptotes you approach with many verdicts. The **floor keeps the loop
  self-correcting** (a buried item that never appears can never collect the
  thumbs-up that would exonerate it — the floor is the explore/exploit
  guarantee). The **ceiling protects the anti-repetition mission** (uncapped
  favorites would collapse the pool onto themselves). Max spread 1.4/0.6 ≈
  2.3× — deliberately about the same loudness as recency (~2× for
  worn-yesterday), because feedback is the noisier signal.
- **No time window, no mode filter** on the verdict fetch: taste is global
  and slow-moving (unlike recency). Feedback time-decay (~90-day half-life)
  can be added later without schema changes if old verdicts feel stale.
- **Applies everywhere** — including small categories. The #44 exemption
  lifts *rotation pressure*, not *preference*: disliking your only sandals is
  signal.
- Verdicts come from two channels writing the same `outfit_history.feedback`
  column (+1 / −1, latest write wins): emailed HMAC-signed links (#39,
  `GET /feedback/{token}`, token IS the auth) and authed web thumbs (#41,
  `POST /outfits/{history_id}/feedback`, which can also *clear* with
  verdict 0 — email links can't).
- **Attribution-aware blame (#60)**: an optional 👎 follow-up (chips on
  TodayOutfit via `POST /outfits/{history_id}/attribution`; the email 👎
  landing page grows the same chips via `POST /feedback/{token}/attribution`)
  records `feedback_reason` + optional named items + free text.
  `specific_items` → the full unit of blame lands on the named culprits only;
  `combination` / `weather` / `occasion` → **zero item blame** (the items are
  exonerated; the signal feeds Stage 5's avoid-list instead — except
  `weather`, which is recorded only for now). Bare 👎s keep the smear; 👍s
  are never attributed. Flipping or clearing a verdict wipes attribution.
  Mode-scoped multipliers deliberately deferred (months of data away).

## Stage 4 — The draw, then floors

**Weighted sampling without replacement** (Efraimidis–Spirakis): for each
item draw `u ~ Uniform(0,1)`, rank everything by `key = log(u)/w`
descending, take the top `ceil(0.7 × n)` (`SAMPLE_FRACTION = 0.7`).

Why this works: `log(u) < 0` always, so larger `w` pulls the key toward 0 —
weight and rank move together, `u` supplies the randomness. Taking the top-k
of these keys is *provably equivalent* to k sequential weighted draws with
renormalization after each removal, computed in one pass. Equivalent form:
rank by `u^(1/w)`; the log/division version is the numerically nicer way to
get the same ordering.

**Category floors (#16)** then top the pool up — the eviction backstop. Even
unweighted, a 0.7 draw excludes any given item ~30% of days — so a 2-item
category is wholly evicted ≈9% of days and falls below a floor of 2 about
half of them; with bad recency luck, more. The fix:

```
tops ≥ 3 · bottoms+dresses ≥ 3 · footwear ≥ 2 · outerwear ≥ 1
```

Mechanism: the E–S sort already ranked *every* item, so the not-sampled
remainder is a priority-ordered waiting list. Each deficient floor group
promotes its **best-ranked excluded items**, in order, until the floor is met
or the category is exhausted. So promotion respects the same recency ×
feedback lottery — floors change *whether* a category survives, never *which*
items represent it. The pool grows by the deficit (never evicts a winner).
Floors run *after* the gate, so physics outranks floors.

Two deliberate deviations from old issue #16's sketch: the outerwear floor is
**unconditional**, not weather-gated — pool inclusion costs nothing (a coat
in the pool on a hot day is just an item Claude ignores), and it avoids
threading weather into the sampler. And there's **no rain-item floor** — no
rain-appropriateness attribute exists in the schema to key it on.

Finally the pool is **shuffled** — the original #15 motivation: in a stable
id-order, the model anchors on whatever is at the top.

## Stage 5 — Claude proposes candidates, deterministic selection picks (two-stage lite, #63)

The pool (with `warmth` in `WARDROBE_FIELDS`) + today's weather + modes go to
the model — still **one call**, but it returns `CANDIDATES_PER_OUTFIT = 3`
candidate outfits per entry, ordered best-first and meaningfully distinct.
Then `_select_candidates` (code, not an LLM) takes the first candidate per
entry that (1) doesn't exact-set-match a **combination-attributed 👎**
(`blocked_combos` — a recorded known-bad fact, so it's enforced
deterministically per the organizing principle, not asked for in prose) and
(2) passes structural validation. Every rejection is logged with its exact
reason, and the sampled candidate pool is logged at the top of each run, so
"why did/didn't item X appear?" always has an answer in the Actions/Render
logs. Fallbacks: no structurally-valid candidate → the first non-blocked one
goes through the #46 repair machinery as before; *every* candidate blocked →
the entry becomes a mode skip (serving a known-bad combo would defeat the
filter). An **LLM reranker is deliberately absent**: it would grade homework
it just wrote, at 2× cost inside the cron path — deferred until #30 can
measure it.

Prompt rules that interact with the sampler:

- **Layered warmth** (#18): combined outfit warmth should suit the high/low —
  this soft, compositional reasoning is the *replacement* for any item-level
  weather weighting (only the model can know a tee is a base layer today).
- **Slot omission** (#43): if nothing in the pool suits a slot for the mode,
  omit the slot and say so in `reasoning` — never force an off-mode item.
- **Recent feedback context** (#59): the user message also carries up to 5
  disliked and 5 liked outfits from the last 7 days (same window as recency —
  one episodic horizon), each as mode + date + item names
  (`recent_feedback_outfits` in `outfit_history.py`, rendered by
  `_feedback_block` in `claude.py`). Dislikes are an avoid-list for similar
  assemblies — the *combination-level* memory the per-item multiplier (Stage
  3) structurally can't carry. Likes are captioned style-direction-only with
  an explicit don't-recreate instruction, so they can't fight the
  anti-repetition machinery (recency just suppressed those exact items; the
  model must not chase near-substitutes). Injected into the uncached user
  message — the system prompt stays byte-identical for prompt caching. The
  #46 repair calls omit the block: they fix structure, not taste.
  Attribution (#60) refines the dislike lines: `weather`-attributed 👎s are
  dropped (feedback on the forecast call, not the outfit),
  `specific_items` ones name just the culprits, and `combination` /
  `occasion` ones carry a reason tag plus any free-text note — a
  high-confidence avoid entry instead of a guess.
- **Structural validation** (#46): pure `validate_outfit` (≤1 bottoms, ≤1
  footwear, no dupe/unknown ids; no minimums — omission stays valid) → up to
  `MAX_REPAIR_ATTEMPTS = 2` *targeted* repair calls quoting the violations
  back → deterministic `drop_extras` fallback. The daily email can never fail
  on a structural slip; repairs log warnings (grep the Actions logs for the
  rate).

Each non-skip outfit is logged to `outfit_history` (one row per mode per
day), which closes the loop: today's picks are tomorrow's recency scores and,
once thumbed, the feedback multipliers.

---

## Worked example (real numbers)

Item in yesterday's 👍-thumbed 4-item Smart-casual outfit, requested again
today for Smart casual:

```
recency:   s = 0.85 (one appearance, 1 day ago)   → factor = 1/1.85 ≈ 0.54
feedback:  ups = ¼ → score = 1.25/2.25 ≈ 0.556    → mult ≈ 1.044
weight:    w ≈ 0.54 × 1.044 ≈ 0.56                (vs 1.0 for a fresh, unrated item)
```

Rotation pressure (−46%) dominates one day of goodwill (+4.4%) — by design;
taste only wins through accumulation. The first real verdicts (2026-06-10,
3 outfits) produced multipliers 0.943–1.044: gentle nudges, prior-dominated.

## Constants (and their epistemic status)

All in `outfit_history.py` next to each other; all are **educated defaults**,
tunable on evidence once an eval harness (#30) exists.

| Constant | Value | Meaning |
|---|---|---|
| `HISTORY_WINDOW_DAYS` | 7 | recency lookback |
| `DAILY_DECAY` | 0.85 | ≈4-day half-life of rotation pressure |
| `SAMPLE_FRACTION` | 0.7 | share of wardrobe Claude sees |
| `SMALL_CATEGORY_MAX` | 5 | ≤ this many available ⇒ recency-exempt (calibrated: footwear is exactly 5) |
| `FEEDBACK_FLOOR` / `FEEDBACK_CEILING` | 0.6 / 1.4 | explore-guarantee / anti-repetition guard |
| `CATEGORY_FLOORS` | 3/3/2/1 | tops / bottoms+dresses / footwear / outerwear |
| `HOT_GATE_LOW_C` / `COLD_GATE_HIGH_C` | 25 / −5 | (weather_gate.py) extremes thresholds |

Backstop interaction worth remembering: `SAMPLE_FRACTION = 0.7` keeps 70% of
the wardrobe daily, so even floor-weight (0.6×) items appear regularly
regardless of everything above.

## Deliberately out of scope / future iteration ideas

Decided against *for now*, with the trigger that would revisit each:

- **Pairing effects** ("each piece fine, together wrong") — the revisit
  trigger fired 2026-06-12 and the whole chain shipped same day: #59 (prompt-
  level episodic avoid-list), #60 (attribution marks combination 👎s
  explicitly), #63 (deterministic candidate filter hard-blocks them).
  *Statistical* combination memory (estimating pair effects from data) stays
  out of scope. #17 (dedup exact outfit repeats) is the same set-hash
  mechanism with "recent repeats" as the blocklist source — decide there.
- **Jaccard-overlap blocking** — the #63 filter is exact-set match v1; a
  near-match (blocked combo plus one extra accessory) sails through. Loosen
  to high-Jaccard overlap only if near-misses actually show up in practice.
- **LLM reranking of candidates** — no information advantage over the
  generator (same context), 2× cost, new failure point in the cron path;
  revisit only when #30 can measure whether it improves picks.
- **Joint estimation** (regression of verdicts on item indicators, instead of
  smoothed counting) — needs months of verdicts before it beats the smoothed
  counts; revisit after the eval harness (#30).
- **Feedback time-decay** (~90-day half-life) — taste is slow-moving; drops
  in later without schema changes if old verdicts feel stale.
- **Soft weather-fit multiplier** — deliberately *deleted*, not deferred (see
  D4 in the design doc): the middle of the fit curve is compositional, a
  curve needs tuning data we don't have, and the failure asymmetry favors the
  gate + prompt (a missed absurd item is caught by the prompt; a wrongly
  suppressed base layer is unrecoverable downstream).
- **Rain-appropriate floor** — needs a rain attribute on items first.
- **Constant tuning** — every number above is by-inspection; the principled
  path is #30 (eval harness) → measure → tune.
- **Mode-relevant scarcity** — floors and the #44 exemption see *category*
  scarcity, not *mode* scarcity (they can't know only 1 of 5 footwear suits
  Elevated). #43's slot omission is the current coverage for that gap.

## Where everything lives

| What | File | Tests |
|---|---|---|
| Pipeline orchestration | `backend/services/recommend.py` | (e2e via `RUN_E2E=1`) |
| Sampling: recency, feedback, draw, floors | `backend/services/outfit_history.py` | `tests/test_sampling.py` |
| Recent-feedback prompt context (#59) | `outfit_history.py` (fetch/shape) + `claude.py` (render) | `tests/test_feedback_context.py` |
| Extremes gate | `backend/services/weather_gate.py` | `tests/test_weather_gate.py` |
| type→category map | `backend/services/categories.py` | (covered via sampling/validation tests) |
| Outfit prompt, validation, repair | `backend/services/claude.py` | `tests/test_validation.py` |
| Candidate selection + 👎-combo blocklist (#63) | `claude.py` (`_select_candidates`) + `outfit_history.py` (`blocked_combos`) | `tests/test_candidates.py` |
| Email feedback tokens | `backend/services/feedback_token.py` | `tests/test_feedback_token.py` |
| 👎 attribution (#60): validation + write | `outfit_history.py` (`record_attribution`) | `tests/test_attribution.py` |
| Web feedback + attribution endpoints | `backend/routers/outfits.py` | — |
| Email feedback GET + attribution landing page | `backend/routers/feedback.py` | — |
| Daily job + modes | `jobs/daily_outfit.py` | — |
| Calendar → modes (#64) | `backend/services/calendar.py` + `claude.py` (`classify_modes`) | `tests/test_calendar.py` |
