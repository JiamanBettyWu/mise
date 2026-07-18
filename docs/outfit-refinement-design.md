# Multi-turn outfit refinement — design (#145)

Scoped 2026-07-17. Sibling: #144 (email one-tap refine links) — same feature,
two front doors; #145 ships first and #144 reuses its persistence helper.

## Problem

Today's Outfit is one-shot: if a pick is *almost* right, the only lever is full
regeneration, which throws away the good parts along with the bad. We want a
follow-up box per outfit — "swap the shoes for something more comfortable",
"actually I'm biking today" — that refines instead of regenerates.

This is also the third production LangGraph and the main learning payload:
**checkpointers / conversation state**, which neither the trip planner nor
preference inference exercises.

## Why a graph at all (first principles)

The existing pipeline in `services/recommend.py` is already cleanly split into
*context assembly* (weather → extremes gate → weighted sampling → history
signals) and the *Claude pick* (`claude.recommend_outfits`). A refinement turn
wants to **reuse the assembled context but change one instruction and pin most
of the outfit** — re-running sampling every turn would let the outfit drift
because the pool changed under it. That "carry state across turns" requirement
is exactly what a checkpointed `StateGraph` provides; plain function calls
would need us to hand-roll the same session store.

## Graph shape (`services/outfit_refine.py`)

```
START → load_context → route ──(refine)────→ refine_outfit ──→ persist → END
                              └─(regenerate)→ regenerate ────↗
```

State (TypedDict), keyed by `thread_id = history_id`:

- `history_id`, `mode` (label + description), `weather`
- `current_items` (item_ids) + `reasoning` — the outfit being refined
- `candidate_pool` — assembled once on the first turn, reused on later ones
- `turns` — the user's refinement messages so far (for prompt context)

Nodes:

- **`load_context`** — first turn only (checkpointer makes later turns skip
  the work: pool already in state). Rebuilds context from the history row:
  re-runs weather + gate + sampling, then **force-includes the row's current
  `item_ids` in the pool** so the outfit under refinement is always
  addressable. Decision: rebuild rather than persist the original pool at
  generation time — no change to the generate path, and a slightly different
  pool is harmless since the current outfit is pinned in.
- **`route`** — a Haiku call classifying the user message: *refine* (keep the
  outfit, modify targeted slots) vs *regenerate* (constraints changed — the
  pool itself may be wrong now). Conditional edge dispatches on the returned
  label, mirroring the trip planner's `check_gaps` router + its
  Haiku-for-cheap-decisions pattern (`plan_purchase_queries_node`). On any
  routing failure, default to *refine* (cheaper, non-destructive).
- **`refine_outfit`** — Sonnet call: current outfit + instruction + turn
  history, told to change only what's asked, choosing replacements from
  `candidate_pool`. Must go through the same validation seam as generation
  (`_select_candidates`-style checks): `blocked_combos` (#60) and
  `recent_combos` (#17) still apply — a refine must not be able to produce a
  👎-attributed or recently-repeated combination.
- **`regenerate`** — re-runs the full pipeline for this one mode with the
  accumulated turn messages appended as `notes` (the #135 seam), then
  refreshes `candidate_pool` in state.
- **`persist`** — updates the **existing** `outfit_history` row in place:
  `item_ids` ← the new set, and **clears any existing verdict** (the verdict
  was about the old items — same answer as #144's open question). This
  row-update helper lives in `outfit_history.py` and is the shared piece #144
  will reuse.

## History semantics (decided in the issue, confirmed)

**Final version only.** One row per mode per day stays true; thumbs apply to
whatever the user saw last. The refinement trail is not kept in
`outfit_history` — the turn history lives only in the checkpointer and dies
with it.

**Cohort hygiene (#143/#135):** `persist` adds `"refined": true` to the row's
`config` label so the diversity report can separate refined rows from pristine
ones — otherwise refinement quietly pollutes config-cohort comparisons. The
refine prompt itself does **not** join the prompt_sha registry; only
`OUTFIT_SYSTEM_PROMPT` is versioned that way, deliberately.

## Checkpointer: in-memory `MemorySaver`

A refinement conversation is minutes long; losing it on a Render restart costs
one re-generate. A Supabase-backed `BaseCheckpointSaver` is real work for zero
product value at this scale. Render runs a single worker, so per-process
memory is coherent today — this is one of the items the
[multi-user plan](multi-user-plan.md) would revisit (along with bounding the
saver's memory if threads ever accumulate).

## API

`POST /outfits/{history_id}/refine  {"message": "..."}` → same response shape
as one hydrated outfit from `recommend()` (items + reasoning + history_id),
plus the route taken (`refined` | `regenerated`) for the UI.

- `history_id` doubles as the LangGraph `thread_id` — no session plumbing.
- **Scope guard, server-side:** 404/409 unless the row's date is today.
  Refinement is for today's generated outfits only, never historical ones.
- Blocking JSON for v1 — a single-mode refine is one Sonnet call, not a
  pipeline; no SSE.

## Metering

Two new `llm_usage` call_types via the existing `create_tracked` seam:
`outfit_refine_route` (Haiku) and `outfit_refine` (Sonnet). Regenerate-path
calls keep their existing `call_type` since they run the normal pipeline.

## Frontend

Per-outfit-card "Refine" affordance on TodayOutfit opening a small chat input
under that card — refinement is per mode/row, not global. Each turn swaps that
card's items in place; existing thumbs UI keeps working against the same
`history_id` (and reflects the verdict reset). Design-system details per
DESIGN.md at implementation time.

## Out of scope (v1)

- Persistent (DB-backed) checkpointing.
- Refining historical days.
- Keeping the refinement trail.
- SSE/streaming.
- #144's email links — separate PR on top of the shared persist helper.
