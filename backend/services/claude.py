import base64
import json
import os
from functools import lru_cache

from anthropic import Anthropic

from services.image import ensure_under_limit

MODEL = "claude-sonnet-4-6"

TAGGING_SYSTEM_PROMPT = """You are a clothing-tagging assistant for a personal wardrobe app.

Given a photo of a single clothing item, return a JSON object with these fields:

- name: short descriptive name, 3-7 words, e.g. "Navy wool blazer" or
  "Cream cable-knit cardigan". No leading articles. No more than 7 words.
- type: one of: jacket, coat, vest, shirt, t-shirt, sweater, blouse, dress,
  skirt, trousers, jeans, shorts, shoes, boots, sneakers, sandals, bag, scarf,
  hat, belt, accessory, other. Pick the closest match.
- color: primary color in plain English, e.g. "navy blue", "off-white", "burgundy"
- formality: exactly one of: casual, smart-casual, formal
- season: exactly one of: spring, summer, fall, winter, all-season
- fabric: best guess at material, e.g. "cotton", "wool", "denim", "leather",
  "synthetic". Use "unknown" if you genuinely cannot tell.
- description: 1-5 sentences describing notable details — silhouette, fit,
  pattern, hardware, neckline, distinctive features. Skip generic filler.
- brand: only set if a logo or label is clearly visible AND legible. Otherwise
  return null. Do not guess.

Return ONLY the JSON object, no commentary, no markdown fences. The JSON must
be parseable. If multiple items appear in the photo, tag the most prominent one.
"""


@lru_cache(maxsize=1)
def client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def tag_clothing_photo(image_bytes: bytes, mime_type: str) -> dict:
    """Send photo to Claude vision; return parsed tag dict.

    Uses prompt caching on the system prompt so repeat tagging is cheaper.
    """
    image_bytes, mime_type = ensure_under_limit(image_bytes, mime_type)
    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    resp = client().messages.create(
        model=MODEL,
        max_tokens=512,
        system=[
            {
                "type": "text",
                "text": TAGGING_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": mime_type,
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": "Tag this item."},
                ],
            }
        ],
    )

    return parse_json(resp)


OUTFIT_SYSTEM_PROMPT = """You are a personal stylist. Given today's weather and
a wardrobe inventory, recommend complete outfits.

Each outfit should:
- Be weather-appropriate (layers for cold, breathable for heat, water-resistant
  if rain is likely).
- Be coherent in color, formality, and style.
- Include all the pieces a person would actually wear: top + bottom (or dress)
  + shoes, plus outerwear if needed and any standout accessories.
- Use ONLY items from the inventory. Reference each item by its `id`.
- Favor variety across days. The inventory order is randomized and does not
  imply preference; explore the full set rather than defaulting to the first
  few items, unless weather or mode genuinely require a specific piece.

If the user provides a list of MODES, return exactly one outfit per mode in the
SAME ORDER. Each outfit must fit the mode's vibe. Repeat the mode name in the
outfit's `label` field. If no modes are provided, set `label` to an empty string
and return the requested count.

If no suitable outfit can be assembled for a given mode under today's weather
(e.g. the wardrobe lacks elevated pieces, or every option would be wildly
inappropriate for the conditions), DO NOT force a bad suggestion. Instead,
return the entry with `item_ids: []` and a brief `reasoning` that begins with
"No <mode-name> recommendation available today" and explains why in one
sentence. Keep the entry in the same position; do not drop modes. When you
skip a mode this way, `item_ids` MUST be the empty list — never combine the
"No … recommendation available today" reasoning with non-empty item_ids.

Return ONLY a JSON object of the shape:
{
  "outfits": [
    {
      "label": "<mode name or empty string>",
      "item_ids": ["<uuid>", "<uuid>", ...],
      "reasoning": "1-2 sentences"
    },
    ...
  ]
}

No commentary, no markdown fences. The JSON must be parseable.
"""


def recommend_outfits(
    weather: dict,
    wardrobe: list[dict],
    n: int,
    notes: str = "",
    modes: list[dict] | None = None,
) -> list[dict]:
    """Ask Claude for outfit suggestions. Returns list of {label, item_ids, reasoning}.

    If `modes` is provided, returns one outfit per mode in order; `n` is ignored.
    Each mode is a dict with keys `name` and `description`.
    """
    user_blocks = [
        f"Weather: high {weather['temp_high_c']}°C, low {weather['temp_low_c']}°C, "
        f"{weather['conditions']}, "
        f"{int(weather['precip_chance'] * 100)}% precipitation chance, "
        f"wind {weather['wind_kmh']} km/h.",
    ]
    if modes:
        user_blocks.append("Modes (return one outfit per mode, in this order):")
        for m in modes:
            user_blocks.append(f"- {m['name']}: {m['description']}")
    else:
        user_blocks.append(f"Please return exactly {n} outfit{'s' if n != 1 else ''}.")
    if notes.strip():
        user_blocks.append(f"User notes for today: {notes.strip()}")
    user_blocks.append("Wardrobe inventory (JSON):")
    user_blocks.append(json.dumps(wardrobe, ensure_ascii=False))

    resp = client().messages.create(
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": OUTFIT_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "\n\n".join(user_blocks)}],
    )
    parsed = parse_json(resp)
    return parsed.get("outfits", [])


def parse_json(resp) -> dict:
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    return json.loads(text)
