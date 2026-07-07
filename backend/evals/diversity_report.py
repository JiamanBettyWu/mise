"""Ad-hoc recommendation-diversity report over live outfit_history (#118).

Run from the repo root:

    uv --project backend run python backend/evals/diversity_report.py [--days 60]

Read-only diagnosis, no LLM calls, free. Answers "is the recommender
repeating itself, where, and why" over the trailing window: item-usage
concentration, per-category entropy, catalog coverage, repeat gaps, recurring
pairs, and whether feedback multipliers are skewing picks. Companion to the
offline eval: this diagnoses on real history; the eval measures a candidate
fix on frozen scenarios before it ships.
"""

from __future__ import annotations

import argparse
import math
import sys
from collections import Counter, defaultdict
from datetime import date, timedelta
from itertools import combinations
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from dotenv import load_dotenv

# Load the single repo-root .env regardless of cwd.
load_dotenv(Path(__file__).resolve().parents[2] / ".env")

from db.supabase import client as supabase  # noqa: E402
from services.categories import category_of  # noqa: E402


def entropy_ratio(counts: list[int]) -> float:
    """Shannon entropy of the pick distribution / max possible (0..1)."""
    total = sum(counts)
    n = len(counts)
    if total == 0 or n <= 1:
        return 1.0
    h = -sum((c / total) * math.log(c / total) for c in counts if c)
    return h / math.log(n)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=60)
    args = ap.parse_args()
    since = (date.today() - timedelta(days=args.days)).isoformat()

    hist = (
        supabase()
        .table("outfit_history")
        .select("recommended_on,mode,item_ids,feedback")
        .gte("recommended_on", since)
        .order("recommended_on")
        .execute()
        .data
        or []
    )
    items = (
        supabase().table("clothing_items").select("id,name,type").execute().data or []
    )
    by_id = {i["id"]: i for i in items}

    def label(iid: str) -> str:
        it = by_id.get(iid)
        return f"{it['name']} ({it['type']})" if it else f"<deleted {iid[:8]}>"

    print(f"# Diversity report — last {args.days} days ({since} → today)")
    print(f"{len(hist)} outfit rows, catalog size {len(items)}\n")
    if not hist:
        print("No history rows in window.")
        return

    # --- item usage distribution ---
    picks = Counter(iid for r in hist for iid in (r["item_ids"] or []))
    total_slots = sum(picks.values())
    print(f"## Item usage ({total_slots} item-slots, {len(picks)} distinct items)")
    top5_share = sum(c for _, c in picks.most_common(5)) / total_slots
    print(f"Top-5 items' share of all slots: {top5_share:.0%}")
    for iid, c in picks.most_common(10):
        print(f"  {c:3d}x  {label(iid)}")
    print()

    # --- per-category concentration ---
    print("## Per-category concentration")
    cat_counts: dict[str, Counter] = defaultdict(Counter)
    for iid, c in picks.items():
        it = by_id.get(iid)
        cat = category_of(it["type"]) if it else "other"
        cat_counts[cat][iid] = c
    cat_sizes = Counter(category_of(i["type"]) for i in items)
    for cat, cnt in sorted(cat_counts.items()):
        er = entropy_ratio(list(cnt.values()))
        top_i, top_c = cnt.most_common(1)[0]
        print(
            f"  {cat:11s} used {len(cnt)}/{cat_sizes.get(cat, 0)} items, "
            f"entropy {er:.2f}, top: {label(top_i)} "
            f"({top_c}x, {top_c / sum(cnt.values()):.0%})"
        )
    print()

    # --- coverage / dead inventory ---
    never = [i for i in items if i["id"] not in picks]
    print(
        f"## Coverage: {len(items) - len(never)}/{len(items)} items recommended;"
        f" {len(never)} never picked in window"
    )
    for i in never[:15]:
        print(f"  never: {i['name']} ({i['type']})")
    if len(never) > 15:
        print(f"  ... and {len(never) - 15} more")
    print()

    # --- repeat gaps ---
    print("## Repeat gaps (days between consecutive picks of the same item)")
    last_seen: dict[str, date] = {}
    gaps: list[int] = []
    short_repeats: Counter = Counter()
    for r in hist:
        d = date.fromisoformat(r["recommended_on"])
        for iid in r["item_ids"] or []:
            if iid in last_seen:
                g = (d - last_seen[iid]).days
                if g > 0:
                    gaps.append(g)
                    if g <= 3:
                        short_repeats[iid] += 1
            last_seen[iid] = d
    if gaps:
        gaps.sort()
        med = gaps[len(gaps) // 2]
        pct_le3 = sum(1 for g in gaps if g <= 3) / len(gaps)
        print(f"  {len(gaps)} repeats; median gap {med}d; {pct_le3:.0%} within 3 days")
        for iid, c in short_repeats.most_common(5):
            print(f"  frequent ≤3d repeater: {label(iid)} ({c}x)")
    else:
        print("  no repeats in window")
    print()

    # --- pair co-occurrence ---
    print("## Recurring pairs (same two items in one outfit)")
    pairs = Counter(
        frozenset(p)
        for r in hist
        for p in combinations(sorted(set(r["item_ids"] or [])), 2)
    )
    recurring = [(p, c) for p, c in pairs.most_common(8) if c >= 3]
    if recurring:
        for p, c in recurring:
            a, b = sorted(p)
            print(f"  {c:3d}x  {label(a)} + {label(b)}")
    else:
        print("  no pair appeared 3+ times")
    print()

    # --- feedback vs concentration ---
    print("## Feedback skew (like-rate of top-10 items vs rest)")
    verdicts: dict[str, list[int]] = defaultdict(list)
    for r in hist:
        if r.get("feedback") in (1, -1):
            for iid in r["item_ids"] or []:
                verdicts[iid].append(r["feedback"])

    def like_rate(ids):
        vs = [v for i in ids for v in verdicts.get(i, [])]
        ups = sum(1 for v in vs if v == 1)
        return (ups / len(vs), len(vs)) if vs else (None, 0)

    top10 = [i for i, _ in picks.most_common(10)]
    rest = [i for i in picks if i not in top10]
    for name, group in (("top-10", top10), ("rest", rest)):
        lr, n = like_rate(group)
        if lr is None:
            print(f"  {name:6s}: no verdicts")
        else:
            print(f"  {name:6s}: like-rate {lr:.0%} over {n} verdicts")


if __name__ == "__main__":
    main()
