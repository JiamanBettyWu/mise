"""Recency-decay weighted sampling of the wardrobe candidate pool.

Issue #15. Without this, Claude sees the wardrobe in a stable id-order and
anchors on whatever is at the top — producing the same outfits day after day.
Here we score each item by how recently it was recommended (exponential decay
over a short lookback), then probabilistically sample a subset where recent
items are less likely but never excluded.

Tunables:
  HISTORY_WINDOW_DAYS  how far back the decay reaches
  DAILY_DECAY          per-day multiplicative decay; 0.85 ≈ ~4 day half-life
  SAMPLE_FRACTION      target share of the wardrobe to keep in the pool
  SMALL_CATEGORY_MAX   categories at or below this size skip recency entirely
  FEEDBACK_FLOOR       multiplier at like-rate 0 — exploration guarantee (#42)
  FEEDBACK_CEILING     multiplier at like-rate 1 — anti-repetition guard (#42)
  CATEGORY_FLOORS      minimum per-category presence in the sampled pool (#16)
"""

from __future__ import annotations

import math
import random
from collections import Counter
from datetime import date, timedelta

from db.supabase import client as supabase
from services.categories import category_of

HISTORY_WINDOW_DAYS = 7
DAILY_DECAY = 0.85
SAMPLE_FRACTION = 0.7
SMALL_CATEGORY_MAX = 5
FEEDBACK_FLOOR = 0.6
FEEDBACK_CEILING = 1.4
FEEDBACK_CONTEXT_MAX_PER_VERDICT = 5

# Issue #60: optional 👎 attribution — what the thumbs-down was really about.
# Single-choice; 'specific_items' carries the named culprits alongside.
ATTRIBUTION_REASONS = ("specific_items", "combination", "weather", "occasion")
# Reasons that exonerate the items: the verdict was about the assembly, the
# weather call, or the mode fit — zero per-item blame in the multipliers.
ITEM_EXONERATING_REASONS = ("combination", "weather", "occasion")

# Issue #16: the SAMPLE_FRACTION draw can evict a small category wholesale
# (the sandals incident's last unshipped mechanism). Each entry is a group of
# categories sharing one floor — dresses satisfy the lower-half requirement
# just like bottoms do. Floors are minimums in the *candidate pool*, not the
# outfit; pool inclusion costs nothing, so outerwear is unconditional rather
# than weather-gated (a coat in the pool on a hot day is just an item Claude
# ignores). Implicitly capped by availability.
CATEGORY_FLOORS = (
    (("tops",), 3),
    (("bottoms", "dresses"), 3),
    (("footwear",), 2),
    (("outerwear",), 1),
)


def sample_wardrobe(
    wardrobe: list[dict],
    modes: list[dict] | None,
    today: date | None = None,
) -> list[dict]:
    """Return a recency-weighted random subset of the wardrobe.

    Items recently recommended in any of today's `modes` are less likely to be
    picked: p ∝ 1 / (1 + recency_score). Items never recommended are uniformly
    likely. With `modes=None`, recency is summed across all modes.

    Items in small categories (≤ SMALL_CATEGORY_MAX available) are exempt
    from recency weighting — see _sampling_weights.
    """
    if not wardrobe:
        return wardrobe

    today = today or date.today()
    mode_names = [m["name"] for m in modes] if modes else None

    scores = _recency_scores(
        modes=mode_names,
        today=today,
    )
    multipliers = _feedback_multipliers(_feedback_rows())
    weights = _sampling_weights(wardrobe, scores, multipliers)

    target_size = max(1, math.ceil(len(wardrobe) * SAMPLE_FRACTION))
    ranked = _ranked_by_sample_key(wardrobe, weights)
    sampled = _apply_category_floors(ranked[:target_size], ranked[target_size:])

    random.shuffle(sampled)
    return sampled


def log_outfits(
    on_date: date,
    mode_items: list[tuple[str, list[str]]],
    weather: dict | None = None,
    notes: str = "",
) -> list[str | None]:
    """Insert one outfit_history row per non-empty (mode, item_ids) pair.

    Empty `item_ids` (the "no recommendation today" skip case) are dropped —
    counting them would phantom-penalize items in future runs.

    `weather` and `notes` are the recommendation-time context (#60): the
    weekly preference-inference job (#62) needs "what was the weather / the
    ask when she judged this", and neither can be backfilled later.

    Returns the inserted row ids aligned with `mode_items` (None at skipped
    positions), so callers can attach feedback links to each outfit (#39).
    PostgREST returns inserted rows in input order.
    """
    rows = [
        {
            "recommended_on": on_date.isoformat(),
            "mode": mode or "(default)",
            "item_ids": item_ids,
            "weather": weather,
            "notes": notes or None,
        }
        for mode, item_ids in mode_items
        if item_ids
    ]
    inserted = (
        supabase().table("outfit_history").insert(rows).execute().data or []
        if rows
        else []
    )
    ids = iter(row["id"] for row in inserted)
    return [next(ids, None) if item_ids else None for _, item_ids in mode_items]


def blocked_combos() -> set[frozenset[str]]:
    """Item-id sets of combination-attributed 👎 outfits (#63).

    A 👎 tagged "the combination" is not a soft preference — it's a recorded
    known-bad fact, so it's enforced deterministically (candidate filter in
    claude._select_candidates) instead of asked for in prose. No time window,
    same reasoning as _feedback_rows: a combination judged bad stays bad
    until the verdict is cleared or flipped (which wipes the attribution).
    Exact-set matching for v1; high-Jaccard overlap is a future refinement.
    """
    rows = (
        supabase()
        .table("outfit_history")
        .select("item_ids")
        .eq("feedback", -1)
        .eq("feedback_reason", "combination")
        .execute()
        .data
        or []
    )
    return {frozenset(row["item_ids"]) for row in rows if row.get("item_ids")}


class AttributionError(ValueError):
    """Invalid attribution payload or row state. `.status` is the HTTP code."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def record_attribution(
    history_id: str,
    reason: str | None,
    item_ids: list[str],
    note: str,
) -> dict:
    """Validate and write a 👎 attribution (#60); shared by both channels.

    The web endpoint and the email landing page differ only in auth
    (X-App-Password vs HMAC token) — semantics live here. Attribution is
    strictly optional and only ever follows a *current* 👎: the verdict
    endpoints wipe these fields on flip/clear, and the guarded update below
    refuses to attach attribution to a row whose verdict changed underneath.

    Raises AttributionError with an HTTP-ready status; returns the updated row.
    """
    note = (note or "").strip()
    if reason is not None and reason not in ATTRIBUTION_REASONS:
        raise AttributionError(f"unknown reason {reason!r}", 422)
    if reason is None and not note:
        raise AttributionError("nothing to record — pick a reason or add a note", 422)
    if reason == "specific_items" and not item_ids:
        raise AttributionError("'specific_items' needs at least one item", 422)
    if reason != "specific_items":
        item_ids = []

    res = (
        supabase()
        .table("outfit_history")
        .select("feedback, item_ids")
        .eq("id", history_id)
        .execute()
    )
    if not res.data:
        raise AttributionError("outfit not found", 404)
    row = res.data[0]
    if row.get("feedback") != -1:
        raise AttributionError("attribution applies to a current 👎 only", 409)
    if item_ids and not set(item_ids) <= set(row.get("item_ids") or []):
        raise AttributionError("named items must come from this outfit", 422)

    updated = (
        supabase()
        .table("outfit_history")
        .update(
            {
                "feedback_reason": reason,
                "feedback_item_ids": item_ids or None,
                "feedback_note": note or None,
            }
        )
        .eq("id", history_id)
        .eq("feedback", -1)
        .execute()
    )
    if not updated.data:
        raise AttributionError("verdict changed — attribution not recorded", 409)
    return updated.data[0]


def recent_feedback_outfits(today: date | None = None) -> list[dict]:
    """Recently thumbed outfits, name-hydrated, for prompt context (#59).

    Episodic combination-level memory: the per-item multiplier (#42) smears a
    verdict across items, so a bad *combination* of individually-fine items
    can recur — showing the model the actual assemblies is the cheapest fix.
    Window deliberately reuses HISTORY_WINDOW_DAYS: the prompt's episodic
    memory and the sampler's rotation pressure share one horizon.

    Returns entries shaped by _select_feedback_entries, newest first.
    """
    today = today or date.today()
    cutoff = today - timedelta(days=HISTORY_WINDOW_DAYS)
    rows = (
        supabase()
        .table("outfit_history")
        .select(
            "recommended_on, mode, item_ids, feedback,"
            " feedback_reason, feedback_item_ids, feedback_note"
        )
        .gte("recommended_on", cutoff.isoformat())
        .not_.is_("feedback", "null")
        .order("recommended_on", desc=True)
        .execute()
        .data
        or []
    )
    ids = sorted({iid for row in rows for iid in (row.get("item_ids") or [])})
    names: dict[str, str] = {}
    if ids:
        res = supabase().table("clothing_items").select("id, name").in_("id", ids).execute()
        names = {r["id"]: r["name"] for r in (res.data or [])}
    return _select_feedback_entries(rows, names)


def _select_feedback_entries(
    rows: list[dict],
    names_by_id: dict[str, str],
) -> list[dict]:
    """Pure: shape verdict rows into capped per-polarity prompt entries.

    Expects rows newest-first; keeps at most FEEDBACK_CONTEXT_MAX_PER_VERDICT
    per polarity. Deleted items (no name) are skipped silently; an entry with
    no surviving names is dropped — a list of nothing teaches nothing.
    Non-±1 verdicts are skipped defensively, same as _feedback_multipliers.

    Attribution (#60) refines dislikes: 'weather' ones are dropped entirely
    (feedback on the forecast call, not the outfit — recorded only for now);
    'specific_items' ones name just the culprit items, a higher-confidence
    avoid entry than the whole assembly. Reason and note ride along so the
    prompt can say *why* the outfit was disliked.
    """
    picked: list[dict] = []
    counts = {1: 0, -1: 0}
    for row in rows:
        verdict = row.get("feedback")
        if verdict not in counts or counts[verdict] >= FEEDBACK_CONTEXT_MAX_PER_VERDICT:
            continue
        reason = row.get("feedback_reason") if verdict == -1 else None
        if reason == "weather":
            continue
        ids = row.get("item_ids") or []
        if reason == "specific_items":
            ids = row.get("feedback_item_ids") or ids
        item_names = [names_by_id[iid] for iid in ids if iid in names_by_id]
        if not item_names:
            continue
        counts[verdict] += 1
        picked.append(
            {
                "date": row["recommended_on"],
                "mode": row["mode"],
                "verdict": verdict,
                "item_names": item_names,
                "reason": reason,
                "note": (row.get("feedback_note") if verdict == -1 else None) or None,
            }
        )
    return picked


def _sampling_weights(
    wardrobe: list[dict],
    scores: dict[str, float],
    multipliers: dict[str, float],
) -> list[float]:
    """Pure: per-item sampling weights, w = recency_factor × feedback_mult.

    Recency factor is 1 / (1 + recency_score), except — issue #44 (the
    sports-sandals incident) — rotation pressure only makes sense when
    substitutes exist. Items in categories with ≤ SMALL_CATEGORY_MAX
    *available* items get recency factor 1.0 — the same as never-recommended —
    so "you wore the good shoes yesterday" stops evicting the only viable pair.
    Counts are over the wardrobe passed in (already availability- and
    travel-filtered), and the category map is the closed `type` vocabulary
    in services/categories.py.

    The feedback multiplier (#42) applies to every item regardless of
    category size: the small-category exemption is about rotation pressure,
    not preference. Unrated items get exactly 1.0.
    """
    counts = Counter(category_of(item.get("type", "")) for item in wardrobe)
    weights = []
    for item in wardrobe:
        recency = (
            1.0
            if counts[category_of(item.get("type", ""))] <= SMALL_CATEGORY_MAX
            else 1.0 / (1.0 + scores.get(item["id"], 0.0))
        )
        weights.append(recency * multipliers.get(item["id"], 1.0))
    return weights


def _feedback_multipliers(rows: list[dict]) -> dict[str, float]:
    """Pure: beta-smoothed per-item like-rate → bounded weight multiplier (#42).

    Each outfit verdict is a noisy label on every item in it, weighted
    1/len(item_ids) so one tap distributes one unit of credit/blame
    (docs/feedback-loop-design.md, D2):

        score_i = (ups_i + 1) / (ups_i + downs_i + 2)   # Laplace prior = 0.5
        mult_i  = FLOOR + (CEILING − FLOOR) × score_i   # [0,1] → [0.6, 1.4]

    Attribution (#60) de-noises the labels: a 👎 attributed to the
    combination / weather / occasion exonerates the items (zero blame —
    the signal lives elsewhere), and one attributed to specific items puts
    the full unit of blame on the named culprits only. Bare 👎s keep the
    smear; 👍s are never attributed and keep theirs.

    Items with no verdicts are absent from the result; callers default them
    to 1.0, so behavior without feedback is unchanged (D3).
    """
    ups: dict[str, float] = {}
    downs: dict[str, float] = {}
    for row in rows:
        item_ids = row.get("item_ids") or []
        verdict = row.get("feedback")
        if not item_ids or verdict not in (1, -1):
            continue
        if verdict == -1:
            reason = row.get("feedback_reason")
            if reason in ITEM_EXONERATING_REASONS:
                continue
            if reason == "specific_items":
                named = [iid for iid in (row.get("feedback_item_ids") or []) if iid in item_ids]
                item_ids = named or item_ids
        credit = 1.0 / len(item_ids)
        bucket = ups if verdict == 1 else downs
        for iid in item_ids:
            bucket[iid] = bucket.get(iid, 0.0) + credit

    span = FEEDBACK_CEILING - FEEDBACK_FLOOR
    return {
        iid: FEEDBACK_FLOOR
        + span * (ups.get(iid, 0.0) + 1.0) / (ups.get(iid, 0.0) + downs.get(iid, 0.0) + 2.0)
        for iid in set(ups) | set(downs)
    }


def _feedback_rows() -> list[dict]:
    """All outfit rows carrying a verdict.

    No window or mode filter, unlike _recency_scores: taste is global and
    slow-moving, and feedback time-decay is deliberately out of scope (D2).
    """
    return (
        supabase()
        .table("outfit_history")
        .select("item_ids, feedback, feedback_reason, feedback_item_ids")
        .not_.is_("feedback", "null")
        .execute()
        .data
        or []
    )


def _recency_scores(
    modes: list[str] | None,
    today: date,
) -> dict[str, float]:
    """For each item id, sum DAILY_DECAY^(days_ago) over the lookback window.

    Per-mode scoring: an item used heavily in Smart Casual but never in
    Athleisure scores high only against today's modes that include Smart Casual.
    With multiple modes today, scores are summed across them — items reused
    across several of today's modes get penalized most.
    """
    cutoff = today - timedelta(days=HISTORY_WINDOW_DAYS)

    q = (
        supabase()
        .table("outfit_history")
        .select("recommended_on, mode, item_ids")
        .gte("recommended_on", cutoff.isoformat())
    )
    if modes:
        q = q.in_("mode", modes)
    rows = q.execute().data or []

    return _aggregate_scores(rows, today)


def _aggregate_scores(rows: list[dict], today: date) -> dict[str, float]:
    """Pure: turn outfit_history rows into per-item decayed-occurrence counts."""
    scores: dict[str, float] = {}
    for row in rows:
        days_ago = (today - date.fromisoformat(row["recommended_on"])).days
        weight = DAILY_DECAY**days_ago
        for iid in row.get("item_ids") or []:
            scores[iid] = scores.get(iid, 0.0) + weight
    return scores


def _ranked_by_sample_key(items: list[dict], weights: list[float]) -> list[dict]:
    """Efraimidis–Spirakis weighted ranking without replacement.

    For each item draw u ~ Uniform(0, 1) and compute key = log(u) / w; sort
    descending by key. The prefix of length k is exactly a weighted sample of
    size k, so callers can slice — and the suffix is the natural "next in
    line" order the category floors (#16) promote from. Pure stdlib.
    """
    keyed: list[tuple[float, dict]] = []
    for item, w in zip(items, weights):
        if w <= 0:
            continue
        u = random.random()
        key = math.log(u) / w if u > 0 else float("-inf")
        keyed.append((key, item))
    keyed.sort(key=lambda kv: kv[0], reverse=True)
    return [item for _, item in keyed]


def _weighted_sample_without_replacement(
    items: list[dict],
    weights: list[float],
    k: int,
) -> list[dict]:
    if k >= len(items):
        return list(items)
    return _ranked_by_sample_key(items, weights)[:k]


def _apply_category_floors(pool: list[dict], overflow: list[dict]) -> list[dict]:
    """Pure: top up the pool so floor categories keep a minimum presence (#16).

    `overflow` is the rest of the sample ranking, best-first, so promotion
    respects the same recency × feedback priorities as the draw itself —
    floors change *whether* a category survives, not *which* of its items do.
    Floors cap at availability for free (overflow only holds what exists and,
    upstream, what survived the weather gate — physics outranks floors). The
    pool grows by at most the sum of deficits instead of evicting other items.
    """
    pool = list(pool)
    counts = Counter(category_of(item.get("type", "")) for item in pool)
    promoted: set[str] = set()
    for group, floor in CATEGORY_FLOORS:
        have = sum(counts[c] for c in group)
        for item in overflow:
            if have >= floor:
                break
            if item["id"] in promoted:
                continue
            if category_of(item.get("type", "")) in group:
                pool.append(item)
                promoted.add(item["id"])
                have += 1
    return pool
