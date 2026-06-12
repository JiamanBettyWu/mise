# Feedback loop + warmth: design decisions

**Status:** scoped and filed 2026-06-09 — issues #39–#44, plus rewritten #18
and a trigger-fired comment on #16. Shipped: #43 (PR #45), #46
(PRs #47/#48), **#39 (PR #49 — feedback capture live, A in the issue map)**,
**#44 (PR #50 — category-aware recency, F in the issue map)**, **#40 (PR #51 —
warmth attribute, C in the issue map; catalog fully backfilled)**, **#18
(PR #56 — warmth in prompt + extremes gate, D′ in the issue map)**, **#42
(PR #57 — feedback → sampling multiplier, E in the issue map)**, **#41
(PR #58 — web thumbs, B in the issue map)**, **#16 (PR #58 — category floors
in the sampled pool)**. The whole design is now implemented; the loop's
quality is data-dependent (verdict volume) from here.
**Last updated:** 2026-06-12 (D2 pairing-effects trigger fired → #59; the
next wave is scoped in issues #59–#64. #60 shipped same day: optional 👎
attribution de-noises D2's smear — see the addendum in D2 — and
`outfit_history` now records weather + notes at recommendation time for the
weekly inference job, #62. #63 also shipped: 3 candidates per mode + a
deterministic filter that hard-blocks combination-attributed 👎 combos —
the enforcement layer the D2 addendum routes that signal to).

Decision record from the scoping session for recommendation-quality work:
thumbs up/down feedback, an inferred warmth attribute, and how both (plus a
category-aware fix to recency) feed the sampling pipeline. Written so
future-me remembers *why* each choice was made, not just what it was.

---

## The organizing principle

Two different kinds of signal want two different homes:

- **Soft preferences** ("she tends not to love this") → **sampling weights**.
  Probabilistic, accumulates over time, fine to get wrong on any single day.
- **Physical constraints** ("it's 4°C outside") → **model context + hard
  gates**. Closer to correctness requirements; encoding them as stochastic
  nudges makes failures unreproducible and undebuggable.

Rule of thumb: *stochastic weights for preferences, deterministic logic for
physics.* The sampling weight stays a product of bounded factors:

```
w = recency_factor × feedback_factor        # weather fit is NOT a factor here
```

Multiplicative composition means each factor ships and tunes independently.

## Issue map

| Issue | What | Depends on |
|---|---|---|
| A = #39 | Feedback capture, email-first (schema, history ids, signed-token links, `GET /feedback/{token}`, email buttons) | — |
| B = #41 | Web thumbs on TodayOutfit (authed POST, reuses A) | #39 |
| C = #40 | Warmth 1–5 on items (tagging prompt, metadata backfill, editable UI) | — |
| D′ = #18 | Rewritten in place: warmth in prompt + extremes gate (not a soft multiplier) | #40 |
| E = #42 | Feedback factor in sampling (smoothed per-item like-rate → clamped multiplier) | #39 |
| F = #44 | Category-aware recency: no recency weighting for small categories (static type→category map, no schema change) | — |
| G = #43 | Prompt: allow omitting a slot (esp. shoes) when nothing suits the mode, instead of forcing an off-mode item or skipping the mode | — |
| #16 | Category floors in the sampled pool — pre-existing issue; the sports-sandals incident is its motivating case (trigger fired) | — |

Order: **#43 immediately** (one prompt bullet, already drafted), **#39 and
#40 next** (they're the data-collection pieces; every day unshipped is signal
not collected), then #42/#18/#44 once data and fields exist, #41 whenever.

---

## D1 — Email-first capture via signed token links

Email is where the app is actually used most, so it's the primary feedback
surface, not an add-on. An email link is a bare GET: no `X-App-Password`
header, no JS. So feedback links carry their own auth — an HMAC-signed token
encoding `(history_id, verdict, expiry)`, ~15 lines of stdlib `hmac`.

Mechanics that matter:

- `jobs/daily_outfit.py` runs `recommend()` **in-process on the GitHub Actions
  runner** — it never calls the Render API. So the *job* signs tokens and the
  *Render backend* verifies them: `FEEDBACK_SECRET` must match in **three
  places** (repo-root `.env`, Render env, Actions workflow secrets), and the
  job needs `BACKEND_PUBLIC_URL` to build links. Forgetting one of the three
  is the classic silent failure.
- `recommend()` must return `outfit_history` row ids (today `log_outfits()`
  returns nothing) — prerequisite shared with the web UI.
- Endpoint sits **outside** `require_password`; the token is the auth.
  Idempotent — re-clicking overwrites, so you can change your mind.
- Known impurity: a GET that mutates state. Corporate scanners (Outlook
  SafeLinks) auto-click links; Gmail doesn't, and this inbox is Gmail, so
  one-click is acceptable. Escape hatch if ever needed: landing page with a
  confirm button. Blast radius of a leaked link: one verdict on one outfit
  row. Tokens expire after ~14 days anyway.

## D2 — Outfit-level thumbs, smoothed item attribution

Verdicts are **outfit-level** (one tap in an email; item-level UI is fussy).
Weights are item-level, so each outfit verdict is treated as a *noisy label*
on every item in it, aggregated with smoothing — beta-Bernoulli, same math as
smoothed CTR:

```
ups_i   = Σ thumbed-up outfits containing item i     (each weighted 1/len(item_ids))
downs_i = Σ thumbed-down outfits containing item i   (same weighting)

score_i = (ups_i + 1) / (ups_i + downs_i + 2)        # Laplace prior = 0.5
mult_i  = 0.6 + 0.8 × score_i                        # [0,1] → [0.6, 1.4]
```

- The `1/len(item_ids)` weighting makes each outfit distribute one unit of
  credit/blame instead of minting n units.
- Worked example: one thumbs-down on a 3-item outfit → each item gets 1/3
  blame → score 3/7 → mult ≈ 0.94 — gentle, because the prior dominates
  single observations. (An earlier draft said 0.87; that number forgot the
  1/len weighting.) The innocent blazer later in three liked 3-item outfits
  → ups = 1.0 → ≈ 1.13. Items are exonerated or
  convicted by **accumulation, never by a single verdict**.
- No-feedback outfits contribute nothing: silence is absence of evidence,
  not a vote.
- Pure function of `outfit_history` rows → unit-tested in `test_sampling.py`.

**Addendum (2026-06-12, #60):** the noisy-label smear is the *default*, not
the ceiling. An optional 👎 follow-up (chips on TodayOutfit; the email
landing page grows the same chips, reusing the verdict token as auth) records
`feedback_reason` ∈ `specific_items | combination | weather | occasion` plus
optional named items and free text. Consumption: `specific_items` puts the
full unit of blame on the named culprits only; `combination`/`weather`/
`occasion` **exonerate the items entirely** (zero blame — the signal lives at
the assembly/forecast/mode level, and the non-weather ones feed #59's prompt
context instead, reason-tagged). Bare 👎s keep the smear; 👍s are never
attributed. Attribution is strictly optional — a required follow-up would
tax the verdict tap itself, and volume is the whole game. Flipping or
clearing a verdict wipes the attribution (it belongs to the verdict act it
followed). Mode-scoped multipliers stay deferred: at ~3 outfits/day there's
no data to estimate per-(item, mode) anything for months.

Deliberately out of scope: pairing effects ("each piece fine, together
wrong" — needs combination-level memory, adjacent to #17 — **trigger fired
2026-06-12: #59 ships a prompt-level episodic version** (recent thumbed
outfits injected into the outfit prompt's user message) **and #63 the
enforcement version** (combination-attributed 👎s become a deterministic
candidate blocklist; statistical pair estimation still out of scope); joint estimation
(regression of verdicts on item indicators — months of data before it beats
smoothed counting; revisit after the eval harness, #30); feedback time-decay
(taste is slow-moving; a ~90-day half-life drops in later without schema
changes if old verdicts feel stale).

## D3 — Why the multiplier is clamped to [0.6, 1.4]

Three jobs:

1. **The floor keeps the loop self-correcting.** If multipliers could reach
   0, an item buried by two unlucky verdicts stops being sampled — and an
   item that never appears can never collect the thumbs-up that would
   exonerate it. The error becomes permanent because measurement stopped.
   The floor is the exploration guarantee (explore–exploit). It also
   preserves the sampler's founding philosophy from #15: *less likely, never
   excluded*. Want an item actually gone? That's the `available` flag — an
   explicit decision, not an emergent one.
2. **The ceiling protects the sampler's original mission.** Uncapped,
   favorites dominate every draw and the pool collapses onto the same items —
   reintroducing the repetition problem the sampler exists to solve.
   Bounded factors also make total-weight ranges computable from constants
   alone when factors compose.
3. **The numbers set feedback's relative loudness.** Neutral (prior 0.5) maps
   to exactly 1.0, so unrated items behave identically to today — the feature
   is purely additive. Symmetric ±0.4. The real parameter is the ratio:
   1.4/0.6 ≈ 2.3×, max spread between most-loved and most-disliked — roughly
   the same volume as the recency factor (~2× for worn-yesterday), *not
   louder*, because feedback is the noisier signal (outfit-level smeared
   across items).

0.6/1.4 are educated defaults with the same epistemic status as
`DAILY_DECAY = 0.85` — named constants in `outfit_history.py`, tunable on
evidence once the eval harness (#30) exists. Backstop: `SAMPLE_FRACTION =
0.7` keeps 70% of the wardrobe daily, so even floor-weight items appear
regularly.

## D4 — Weather fit: warmth in the prompt + extremes gate, NOT a soft sampling multiplier

This rewrites #18 rather than implementing it as written. A hard gate is the
step-function limit of #18's multiplier (0 at the absurd tails, 1.0
elsewhere) — the disagreement is only about the *soft middle*, which we
delete on purpose:

1. **The middle of the fit curve is compositional.** A warmth-1 tee scores
   "bad fit" on a 3°C day — but it's the base layer under the sweater and
   coat. Item-level weather scoring is *anti-correlated* with usefulness for
   layering pieces: the colder it gets, the more it starves the model of
   exactly the light layers cold outfits are built from. Only Claude can
   reason about composition, so hand it the numbers (warmth in
   `WARDROBE_FIELDS` + one prompt line about layered total warmth).
2. **Reproducibility.** With soft weather weights the daily pool is a random
   draw from recency × feedback × weather; "why wasn't the coat shown?" has
   only a probabilistic answer. A gate is deterministic and unit-testable
   ("warmth-5 never sampled when the low ≥ 25°C").
3. **A curve needs tuning data we won't have.** Shape/width/floor interact
   multiplicatively with the other factors; at 3 outfits/day with no evals,
   prefer two thresholds with plain-language meaning, set by common sense.

Failure-mode asymmetry that seals it: if the gate *misses* an absurd item,
the prompt is the backstop and Claude won't pick it. If a soft multiplier
*wrongly suppresses* a base layer, the model never sees it and nothing
downstream recovers. Honest cost: inferred warmth off by ±1 near a hard
threshold flips inclusion where a curve degrades gracefully — mitigated by
generous bands (gate only clear absurdities) and warmth being UI-editable
(misratings are fix-on-sight).

**Season is demoted to display metadata.** It's a human-assigned categorical
that multi-season items and weather-specific gear (rain jackets) break. No
logic should depend on it; warmth is the signal.

## D5 — Warmth inference: metadata-only, fill-nulls-only, UI-editable

- New items: the vision-tagging prompt also returns warmth.
- Existing items: one-off backfill from type + fabric + description — no
  photo re-reads needed.
- Inference **only fills nulls**; a hand-set value in the UI is never
  overwritten by re-tagging. Manual corrections stick.

## D6 — Category-aware recency (the sports-sandals incident)

Observed 2026-06: Elevated mode recommended sports sandals. Catalog evidence
(queried 2026-06-09, 64 items): exactly 5 footwear items, of which only ONE —
the smart-casual ballet flats — can plausibly carry an elevated outfit (the
rest: 2 casual sneakers, sport sandals, flip-flops). With `SAMPLE_FRACTION =
0.7`, the flats are dropped from the pool ~30% of days even *unweighted*,
worse the day after being recommended. The model then faced "outfits must
include shoes" with only sporty options in view, and complied.

**`type` is already the category vocabulary — no inference needed.** The
tagging prompt constrains `type` to a closed list of 22 values
(`claude.py`); category is a static code-level mapping (footwear = shoes /
boots / sneakers / sandals, etc.), a constant dict in `outfit_history.py`.
No schema change, no backfill — issue C stays warmth-only.

Three compounding mechanisms, three fixes:

1. **Recency pressure on scarce categories** → rotation pressure only makes
   sense when substitutes exist. Rule: **small categories get no recency
   weighting at all** (issue F). Simple threshold over a smooth ramp, per
   D4's "parameters validatable by inspection" logic. Calibration: footwear
   count is currently exactly 5, so the threshold is **≤5** ("fewer than 6").
2. **Global sampling can evict an entire small category even unweighted** →
   per-category floors in the sampled pool — pre-existing issue #16, for
   which this incident is the motivating real-world case.
3. **The outfit prompt mandated shoes in every outfit** ("top + bottom (or
   dress) + shoes") while the skip convention was all-or-nothing at the mode
   level — so an off-mode shoe was the model's least-bad way to comply. See
   D7.

Caveat noted for honesty: count thresholds (F) and category floors (#16) see
*category* scarcity, not *mode-relevant* scarcity — neither can know that
only 1 of 5 footwear items suits Elevated. D7 is the layer that covers that
gap.

## D7 — Allow partial outfits: omit a slot rather than force or skip

One prompt change (shipped alongside this doc): an EXCEPTION bullet in
`OUTFIT_SYSTEM_PROMPT` — when nothing in the inventory suits a slot for the
mode and weather, omit the slot and note the gap in `reasoning` ("no suitable
shoes available today"), reserving the full-mode skip for when no coherent
outfit can be built at all. Principle: *an outfit missing shoes beats an
outfit with off-mode shoes.* This is also the only layer that handles
mode-relevant scarcity (see D6 caveat), since the model is the only component
that knows what "dressy enough for Elevated" means. Renderers already handle
arbitrary item lists, so no frontend/email changes needed.
