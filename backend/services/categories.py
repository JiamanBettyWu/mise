"""Static type→category map.

`type` is a closed vocabulary enforced by TAGGING_SYSTEM_PROMPT in
services/claude.py — keep the two in sync when adding types. Shared by outfit
structural validation (issue #46) and category-aware recency (issue #44).
"""

TYPE_CATEGORIES = {
    "jacket": "outerwear",
    "coat": "outerwear",
    "vest": "outerwear",
    "shirt": "tops",
    "t-shirt": "tops",
    "sweater": "tops",
    "blouse": "tops",
    "dress": "dresses",
    "skirt": "bottoms",
    "trousers": "bottoms",
    "jeans": "bottoms",
    "shorts": "bottoms",
    "shoes": "footwear",
    "boots": "footwear",
    "sneakers": "footwear",
    "sandals": "footwear",
    "bag": "accessories",
    "scarf": "accessories",
    "hat": "accessories",
    "belt": "accessories",
    "accessory": "accessories",
    "other": "other",
}

# Categories where a coherent outfit contains at most one item. Tops and
# outerwear are deliberately absent: layering is legitimate.
SINGLE_SLOT_CATEGORIES = ("bottoms", "footwear")


def category_of(item_type: str) -> str:
    return TYPE_CATEGORIES.get((item_type or "").strip().lower(), "other")
