import base64
import json
import os
from functools import lru_cache

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"

TAGGING_SYSTEM_PROMPT = """You are a clothing-tagging assistant for a personal wardrobe app.

Given a photo of a single clothing item, return a JSON object with these fields:

- name: short descriptive name, e.g. "Navy wool blazer"
- type: one of: jacket, coat, shirt, t-shirt, sweater, blouse, dress, skirt,
  trousers, jeans, shorts, shoes, boots, sneakers, sandals, bag, scarf, hat,
  belt, accessory, other. Pick the closest match.
- color: primary color in plain English, e.g. "navy blue", "off-white", "burgundy"
- formality: exactly one of: casual, smart-casual, formal
- season: exactly one of: spring, summer, fall, winter, all-season
- fabric: best guess at material, e.g. "cotton", "wool", "denim", "leather",
  "synthetic". Use "unknown" if you genuinely cannot tell.

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

    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    # Strip any accidental code fences just in case.
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    return json.loads(text)
