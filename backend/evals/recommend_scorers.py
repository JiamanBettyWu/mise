"""Code-based scorers for the daily-recommender eval (#118).

Pure functions over plain dicts, same contract as the trip scorers
(evals/scorers.py): (output, case fields) -> score dict, no weave imports, so
tests/test_recommend_scorers.py covers them in the free suite. Every scorer
returns {"pass": bool, ...details}; conditionally-applicable ones also return
"applicable" so a vacuous pass is distinguishable in the Weave dashboard.

`output` is the eval task's dump of services.recommend.recommend():
{"outfits": [{"label", "item_ids", "types"...}]} — see eval_recommend.py for
the exact shape. Skipped modes (empty item_ids, the "no recommendation
available" case) are excluded from structural checks but reported, so a model
that skips everything can't score a perfect run unnoticed.
"""

from datetime import date

from services.categories import SINGLE_SLOT_CATEGORIES, category_of
from services.outfit_history import SMALL_CATEGORY_MAX
from services.weather_gate import COLD_GATE_HIGH_C, HOT_GATE_LOW_C

# A large-category item recurring within this many days of its last frozen-
# history appearance counts as a repeat — matches the diversity report's
# "% within 3 days" framing, and the median human take on "I just wore that".
MIN_REPEAT_GAP_DAYS = 3

TOP_CATEGORIES = ("tops",)


def _worn_outfits(output: dict) -> list[dict]:
    return [o for o in output.get("outfits", []) if o.get("item_ids")]


def valid_structure(output: dict, catalog: list[dict]) -> dict:
    """Each non-skipped outfit must honor the production structure contract.

    Hard "pass" mirrors validate_outfit (#46): at most one item per
    SINGLE_SLOT_CATEGORIES entry (bottoms, footwear) plus no dress layered
    over a bottom — the eval checks the *final* output, so a failure here
    means the _enforce_structure repair loop itself let something through.

    Deliberately NO minimum counts in the pass: the outfit prompt's EXCEPTION
    rule sanctions omitting a slot the wardrobe can't fill (with a note in
    reasoning), so a missing top/lower/footwear is *reported* as
    incomplete_outfits — visible in Weave, not a failure.
    """
    types_by_id = {item["id"]: item.get("type", "") for item in catalog}
    violations: list[dict] = []
    incomplete: list[str] = []
    for outfit in _worn_outfits(output):
        cats = [category_of(types_by_id.get(iid, "")) for iid in outfit["item_ids"]]
        problems = [
            f"{cat} x{cats.count(cat)}"
            for cat in SINGLE_SLOT_CATEGORIES
            if cats.count(cat) > 1
        ]
        if "dresses" in cats and "bottoms" in cats:
            problems.append("dress + bottom")
        if problems:
            violations.append({"label": outfit.get("label"), "problems": problems})
        has_lower = "dresses" in cats or "bottoms" in cats
        has_top = any(c in TOP_CATEGORIES for c in cats)
        if not (("dresses" in cats or has_top) and has_lower and "footwear" in cats):
            incomplete.append(outfit.get("label"))
    skipped = len(output.get("outfits", [])) - len(_worn_outfits(output))
    return {
        "pass": not violations,
        "violations": violations,
        "incomplete_outfits": incomplete,
        "skipped_modes": skipped,
    }


def items_in_catalog(output: dict, catalog: list[dict]) -> dict:
    """Every recommended item id must exist in the frozen catalog."""
    catalog_ids = {item["id"] for item in catalog}
    unknown = [
        iid
        for outfit in _worn_outfits(output)
        for iid in outfit["item_ids"]
        if iid not in catalog_ids
    ]
    return {"pass": not unknown, "unknown_ids": unknown}


def no_gate_violations(output: dict, weather: dict, catalog: list[dict]) -> dict:
    """No recommended item may violate the extremes gate (#18) for the
    scenario's weather. The gate runs upstream of sampling, so a violation
    means item ids leaked in from outside the candidate pool (a hallucinated
    or repaired-in pick). Vacuous when the scenario isn't extreme."""
    by_id = {item["id"]: item for item in catalog}
    low, high = weather.get("temp_low_c"), weather.get("temp_high_c")
    hot = low is not None and low >= HOT_GATE_LOW_C
    cold = high is not None and high <= COLD_GATE_HIGH_C
    violations = []
    for outfit in _worn_outfits(output):
        for iid in outfit["item_ids"]:
            item = by_id.get(iid)
            if item is None:
                continue  # items_in_catalog's problem, not this scorer's
            if hot and item.get("warmth") == 5:
                violations.append(f"{item['name']}: warmth 5 in heatwave")
            if cold and (
                item.get("warmth") == 1
                and category_of(item.get("type", "")) == "footwear"
            ):
                violations.append(f"{item['name']}: warmth-1 footwear in deep cold")
    return {
        "pass": not violations,
        "applicable": hot or cold,
        "violations": violations,
    }


def repeat_gap(
    output: dict, history: list[dict], catalog: list[dict], today: str
) -> dict:
    """The diversity metric (#118/#135): how much does today's pick repeat the
    frozen history window?

    Per recommended item, gap = days since its last appearance in `history`
    (any mode — repetition is felt across modes). "pass" holds when no item
    from a *large* category (> SMALL_CATEGORY_MAX catalog items) repeats
    within MIN_REPEAT_GAP_DAYS. Small categories (footwear: 5 pairs) are
    exempt from the pass — their repetition is partly arithmetic — but their
    numbers are still reported (footwear_min_gap and the per-item gaps), so a
    variety fix that changes the small-category exemption shows up here.

    fresh_fraction (never-seen-in-window items) and mean_gap are the tuning
    dials' headline numbers: a candidate sampler change should raise both
    without breaking the structural scorers.
    """
    anchor = date.fromisoformat(today)
    last_worn: dict[str, date] = {}
    for row in history:
        d = date.fromisoformat(row["recommended_on"])
        for iid in row.get("item_ids") or []:
            if iid not in last_worn or d > last_worn[iid]:
                last_worn[iid] = d

    by_id = {item["id"]: item for item in catalog}
    cat_sizes: dict[str, int] = {}
    for item in catalog:
        cat = category_of(item.get("type", ""))
        cat_sizes[cat] = cat_sizes.get(cat, 0) + 1

    picked = [iid for o in _worn_outfits(output) for iid in o["item_ids"]]
    gaps: list[int] = []
    early_repeats: list[str] = []
    footwear_gaps: list[int] = []
    fresh = 0
    for iid in picked:
        item = by_id.get(iid, {})
        cat = category_of(item.get("type", ""))
        if iid not in last_worn:
            fresh += 1
            continue
        gap = (anchor - last_worn[iid]).days
        gaps.append(gap)
        if cat == "footwear":
            footwear_gaps.append(gap)
        if gap <= MIN_REPEAT_GAP_DAYS and cat_sizes.get(cat, 0) > SMALL_CATEGORY_MAX:
            early_repeats.append(f"{item.get('name', iid)} ({cat}, {gap}d)")

    n_dupes = len(picked) - len(set(picked))
    return {
        "pass": not early_repeats,
        "early_repeats": early_repeats,
        "fresh_fraction": round(fresh / len(picked), 3) if picked else None,
        "mean_gap_days": round(sum(gaps) / len(gaps), 2) if gaps else None,
        "min_gap_days": min(gaps, default=None),
        "footwear_min_gap_days": min(footwear_gaps, default=None),
        "intra_run_duplicates": n_dupes,
        "items_picked": len(picked),
    }
