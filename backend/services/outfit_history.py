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
    sampled = _weighted_sample_without_replacement(wardrobe, weights, target_size)

    random.shuffle(sampled)
    return sampled


def log_outfits(
    on_date: date,
    mode_items: list[tuple[str, list[str]]],
) -> list[str | None]:
    """Insert one outfit_history row per non-empty (mode, item_ids) pair.

    Empty `item_ids` (the "no recommendation today" skip case) are dropped —
    counting them would phantom-penalize items in future runs.

    Returns the inserted row ids aligned with `mode_items` (None at skipped
    positions), so callers can attach feedback links to each outfit (#39).
    PostgREST returns inserted rows in input order.
    """
    rows = [
        {
            "recommended_on": on_date.isoformat(),
            "mode": mode or "(default)",
            "item_ids": item_ids,
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
        .select("item_ids, feedback")
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


def _weighted_sample_without_replacement(
    items: list[dict],
    weights: list[float],
    k: int,
) -> list[dict]:
    """Efraimidis–Spirakis weighted sampling without replacement.

    For each item draw u ~ Uniform(0, 1) and compute key = log(u) / w; take the
    top-k by key. Exactly equivalent to sequential weighted draws, O(n log k),
    pure stdlib.
    """
    if k >= len(items):
        return list(items)

    keyed: list[tuple[float, dict]] = []
    for item, w in zip(items, weights):
        if w <= 0:
            continue
        u = random.random()
        key = math.log(u) / w if u > 0 else float("-inf")
        keyed.append((key, item))
    keyed.sort(key=lambda kv: kv[0], reverse=True)
    return [item for _, item in keyed[:k]]
