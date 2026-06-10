"""Outfit structural validation + deterministic fallback (issue #46).

Pure functions over (item_ids, {id: type}) so they're testable offline —
see test_validation.py. The repair loop that uses them lives in
services/claude.py next to the model call.
"""

from services.categories import SINGLE_SLOT_CATEGORIES, category_of


def validate_outfit(item_ids: list[str], types_by_id: dict[str, str]) -> list[str]:
    """Return violation messages for one outfit; empty list means valid.

    Deliberately conservative: multiple tops/outerwear are legitimate
    layering, and there are NO minimum counts — omitting a slot with a note
    in `reasoning` is valid behavior (see the EXCEPTION rule in the outfit
    prompt). Empty item_ids (the mode-skip case) is therefore valid too.
    """
    violations: list[str] = []

    seen: set[str] = set()
    for iid in item_ids:
        if iid in seen:
            violations.append(f"duplicate item id {iid}")
        seen.add(iid)

    unique_ids = list(dict.fromkeys(item_ids))
    for iid in unique_ids:
        if iid not in types_by_id:
            violations.append(f"item id {iid} is not in the inventory")

    by_category: dict[str, list[str]] = {}
    for iid in unique_ids:
        if iid in types_by_id:
            by_category.setdefault(category_of(types_by_id[iid]), []).append(iid)
    for category in SINGLE_SLOT_CATEGORIES:
        ids = by_category.get(category, [])
        if len(ids) > 1:
            violations.append(
                f"{len(ids)} {category} items in one outfit "
                f"({', '.join(ids)}) — at most one allowed"
            )
    return violations


def drop_extras(item_ids: list[str], types_by_id: dict[str, str]) -> list[str]:
    """Deterministic fallback when repair calls fail: dedupe, drop unknown
    ids, and keep only the FIRST item per single-slot category (the model's
    first pick), preserving order. Result always passes validate_outfit."""
    kept: list[str] = []
    seen: set[str] = set()
    used_slots: set[str] = set()
    for iid in item_ids:
        if iid in seen or iid not in types_by_id:
            continue
        seen.add(iid)
        category = category_of(types_by_id[iid])
        if category in SINGLE_SLOT_CATEGORIES:
            if category in used_slots:
                continue
            used_slots.add(category)
        kept.append(iid)
    return kept
