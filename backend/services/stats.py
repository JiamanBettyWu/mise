"""Profile stats aggregation (#115).

Pure functions over rows already fetched from Supabase — the endpoint in
routers/profile.py does the queries, this module does the math, and the
offline tests exercise it without a network.

Cost is derived at read time from PRICES (#114 stores tokens only, never
dollars). The four cache columns matter: llm_usage.input_tokens EXCLUDES
cached tokens, and cache writes/reads are priced differently (1.25x / 0.1x
of input), so cost from input+output alone would be wrong for every cached
call.
"""

from datetime import datetime, timedelta, timezone

# $/MTok as (input, cache_write, cache_read, output). Keyed by model-id
# prefix so dated snapshots ("claude-haiku-4-5-20251001") match the bare
# family price. Longest prefix wins.
PRICES = {
    "claude-sonnet-4-6": (3.00, 3.75, 0.30, 15.00),
    "claude-haiku-4-5": (1.00, 1.25, 0.10, 5.00),
}

RANGES = {"7d": 7, "30d": 30, "90d": 90, "all": None}


def range_cutoff(range_key: str, now: datetime | None = None) -> str | None:
    """ISO timestamp for the start of the window, or None for 'all'."""
    days = RANGES[range_key]  # KeyError -> endpoint 422s before calling this
    if days is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).isoformat()


def _price_for(model: str) -> tuple[float, float, float, float] | None:
    best = None
    for prefix, price in PRICES.items():
        if model.startswith(prefix) and (best is None or len(prefix) > len(best[0])):
            best = (prefix, price)
    return best[1] if best else None


def row_cost(row: dict) -> float | None:
    """Estimated dollars for one llm_usage row; None if the model is unpriced."""
    price = _price_for(row.get("model", ""))
    if price is None:
        return None
    p_in, p_write, p_read, p_out = price
    return (
        row.get("input_tokens", 0) * p_in
        + row.get("cache_creation_input_tokens", 0) * p_write
        + row.get("cache_read_input_tokens", 0) * p_read
        + row.get("output_tokens", 0) * p_out
    ) / 1_000_000


def aggregate_usage(rows: list[dict]) -> dict:
    """Sum llm_usage rows into per-call_type buckets + totals.

    Unpriced models still count toward tokens/calls; their cost contributes
    0 and flips has_unpriced so the UI can flag the estimate as partial.
    """
    by_type: dict[str, dict] = {}
    total_tokens = 0
    total_cost = 0.0
    has_unpriced = False

    for row in rows:
        tokens = (
            row.get("input_tokens", 0)
            + row.get("output_tokens", 0)
            + row.get("cache_creation_input_tokens", 0)
            + row.get("cache_read_input_tokens", 0)
        )
        cost = row_cost(row)
        if cost is None:
            has_unpriced = True
            cost = 0.0

        bucket = by_type.setdefault(
            row.get("call_type", "unknown"), {"calls": 0, "tokens": 0, "cost": 0.0}
        )
        bucket["calls"] += 1
        bucket["tokens"] += tokens
        bucket["cost"] += cost
        total_tokens += tokens
        total_cost += cost

    return {
        "by_call_type": by_type,
        "total_tokens": total_tokens,
        "total_cost": round(total_cost, 4),
        "has_unpriced": has_unpriced,
    }


def aggregate_outfits(rows: list[dict]) -> dict:
    """outfit_history rows -> counts, thumbs rate, and item frequency."""
    verdicts = [r["feedback"] for r in rows if r.get("feedback") is not None]
    ups = sum(1 for v in verdicts if v == 1)

    freq: dict[str, int] = {}
    for r in rows:
        for item_id in r.get("item_ids") or []:
            freq[item_id] = freq.get(item_id, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:5]

    return {
        "outfits": len(rows),
        "feedback_count": len(verdicts),
        "thumbs_up_rate": round(ups / len(verdicts), 3) if verdicts else None,
        "top_item_counts": top,  # [(item_id, count)] — endpoint joins names/photos
    }
