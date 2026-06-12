import base64
import json
import logging
import os
from functools import lru_cache

from anthropic import Anthropic

from services.image import ensure_under_limit
from services.validation import drop_extras, validate_outfit

log = logging.getLogger("wardrobe.claude")

MODEL = "claude-sonnet-4-6"

# Outfit structural repair (issue #46): how many targeted re-asks before the
# deterministic drop_extras fallback kicks in.
MAX_REPAIR_ATTEMPTS = 2

# Shared between the vision-tagging prompt and the one-off metadata backfill
# (jobs/backfill_warmth.py) so the two can't drift apart (issue #40).
WARMTH_SCALE = """\
- warmth: integer 1-5 for how much warmth the item provides when worn, or null
  for items that don't meaningfully affect warmth (bags, belts, jewelry-like
  accessories). Scale: 1 = minimal (tank top, shorts, sandals, sheer or linen
  pieces), 2 = light (t-shirt, light blouse, canvas sneakers), 3 = moderate
  (long-sleeve shirt, jeans, light sweater, leather boots), 4 = warm (heavy
  sweater, fleece, lined jacket), 5 = maximum (winter coat, down puffer,
  heavy wool)."""

TAGGING_SYSTEM_PROMPT = f"""You are a clothing-tagging assistant for a personal wardrobe app.

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
{WARMTH_SCALE}
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
- Respect each item's `warmth` rating, 1 (minimal) to 5 (maximum); null means
  the item doesn't affect warmth (bags, belts). The outfit's combined layered
  warmth should suit today's high/low — light pieces for heat; for cold, either
  high-warmth pieces or several lighter layers.
- Be coherent in color, formality, and style.
- Include all the pieces a person would actually wear: top + bottom (or dress)
  + shoes, plus outerwear if needed and any standout accessories.
- EXCEPTION: if nothing in the inventory suits a slot for the mode and weather
  (e.g. no footwear dressy enough for an elevated outfit), OMIT that slot and
  note the gap briefly in `reasoning` (e.g. "no suitable shoes available
  today"). An outfit missing shoes beats an outfit with off-mode shoes. Only
  skip the whole mode when no coherent outfit can be built at all.
- Include at most ONE bottom (trousers, jeans, skirt, or shorts) and at most
  ONE pair of footwear per outfit. Layering multiple tops is fine; doubling
  up single-slot categories is not.
- Use ONLY items from the inventory. Reference each item by its `id`.
- Favor variety across days. The inventory order is randomized and does not
  imply preference; explore the full set rather than defaulting to the first
  few items, unless weather or mode genuinely require a specific piece.
- The user message may include a "Recent outfit feedback" section listing
  outfits the user recently disliked or liked. Avoid recombining assemblies
  similar to a disliked outfit. Liked outfits are style direction ONLY — do
  NOT recreate them or chase near-substitutes; favor variety. Items named
  there may be absent from today's inventory; still use ONLY inventory items.

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
    feedback_entries: list[dict] | None = None,
) -> list[dict]:
    """Ask Claude for outfit suggestions. Returns list of {label, item_ids, reasoning}.

    If `modes` is provided, returns one outfit per mode in order; `n` is ignored.
    Each mode is a dict with keys `name` and `description`.

    `feedback_entries` (from outfit_history.recent_feedback_outfits, #59) is
    rendered into the user message — NOT the system prompt, which must stay
    byte-identical to keep its cache_control prefix valid across calls.
    """
    user_blocks = [_weather_line(weather)]
    if modes:
        user_blocks.append("Modes (return one outfit per mode, in this order):")
        for m in modes:
            user_blocks.append(f"- {m['name']}: {m['description']}")
    else:
        user_blocks.append(f"Please return exactly {n} outfit{'s' if n != 1 else ''}.")
    if notes.strip():
        user_blocks.append(f"User notes for today: {notes.strip()}")
    if feedback_entries:
        user_blocks.append(_feedback_block(feedback_entries))
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
    outfits = parsed.get("outfits", [])
    return _enforce_structure(outfits, wardrobe, weather, modes, notes)


def _feedback_block(entries: list[dict]) -> str:
    """Pure: render recent thumbed outfits (#59) as the prompt section the
    system prompt's feedback bullet refers to.

    Dislikes are the avoid-list; likes are deliberately captioned as style
    direction with a don't-recreate instruction — recency weighting just
    suppressed those exact items, and the model must not fight that by
    hunting near-substitutes. Empty entries → empty string.
    """
    disliked = [e for e in entries if e["verdict"] == -1]
    liked = [e for e in entries if e["verdict"] == 1]
    lines = ["Recent outfit feedback:"]
    if disliked:
        lines.append("Disliked (avoid recombining similar assemblies):")
        lines += [_feedback_line(e) for e in disliked]
    if liked:
        lines.append(
            "Liked (style direction only — do not recreate these exact outfits):"
        )
        lines += [_feedback_line(e) for e in liked]
    return "\n".join(lines) if len(lines) > 1 else ""


# Attributed dislikes (#60) carry their reason into the line — "what to
# avoid" differs by reason: named culprits vs the assembly vs the mode fit.
# Weather-attributed dislikes never reach here (filtered upstream).
_REASON_TAGS = {
    "specific_items": "these specific items were the problem",
    "combination": "the combination, not the items",
    "occasion": "wrong for this occasion/mode",
}


def _feedback_line(e: dict) -> str:
    line = f"- {e['mode']}, {e['date']}: {' + '.join(e['item_names'])}"
    tag = _REASON_TAGS.get(e.get("reason"))
    if tag:
        line += f" ({tag})"
    if e.get("note"):
        line += f" — user note: \"{e['note']}\""
    return line


def _weather_line(weather: dict) -> str:
    return (
        f"Weather: high {weather['temp_high_c']}°C, low {weather['temp_low_c']}°C, "
        f"{weather['conditions']}, "
        f"{int(weather['precip_chance'] * 100)}% precipitation chance, "
        f"wind {weather['wind_kmh']} km/h."
    )


def _enforce_structure(
    outfits: list[dict],
    wardrobe: list[dict],
    weather: dict,
    modes: list[dict] | None,
    notes: str,
) -> list[dict]:
    """Validate outfit structure; repair with feedback, then fall back (issue #46).

    Blind identical retries re-roll correlated dice, so failed outfits get a
    targeted repair call that quotes the violations back. After
    MAX_REPAIR_ATTEMPTS, drop_extras guarantees a structurally valid result —
    a daily email must never fail over a fixable structural slip.
    """
    types_by_id = {item["id"]: item.get("type", "") for item in wardrobe}
    failed: list[tuple[int, dict, list[str]]] = []

    for attempt in range(MAX_REPAIR_ATTEMPTS + 1):
        failed = [
            (i, o, v)
            for i, o in enumerate(outfits)
            if (v := validate_outfit(o.get("item_ids", []), types_by_id))
        ]
        if not failed:
            if attempt:
                log.warning("outfit structure repaired after %d attempt(s)", attempt)
            return outfits
        if attempt == MAX_REPAIR_ATTEMPTS:
            break
        log.warning(
            "outfit validation failed (repair attempt %d/%d): %s",
            attempt + 1,
            MAX_REPAIR_ATTEMPTS,
            "; ".join(
                f"[{o.get('label') or f'#{i}'}] {', '.join(v)}" for i, o, v in failed
            ),
        )
        for (i, _, _), fixed in zip(
            failed, _repair_outfits(failed, wardrobe, weather, modes, notes)
        ):
            if fixed is not None:
                outfits[i] = fixed

    log.warning(
        "outfit validation fallback after %d repair attempts: dropping extras",
        MAX_REPAIR_ATTEMPTS,
    )
    for _, outfit, _ in failed:
        outfit["item_ids"] = drop_extras(outfit.get("item_ids", []), types_by_id)
    return outfits


def _repair_outfits(
    failed: list[tuple[int, dict, list[str]]],
    wardrobe: list[dict],
    weather: dict,
    modes: list[dict] | None,
    notes: str,
) -> list[dict | None]:
    """One targeted re-ask for only the failed outfits. Never raises — any
    API/parse error is logged and reported as no-fix so the caller can retry
    or fall back."""
    mode_by_name = {m["name"]: m for m in (modes or [])}
    blocks = [
        "Your previous outfit response contained structural violations. Return "
        'corrected versions of ONLY the outfits listed below, in this order, as '
        '{"outfits": [...]} in the usual format. Keep each outfit\'s label, fix '
        "the violations, and keep the outfit coherent for its mode and the weather.",
        _weather_line(weather),
    ]
    if notes.strip():
        blocks.append(f"User notes for today: {notes.strip()}")
    for i, outfit, violations in failed:
        label = outfit.get("label") or f"outfit at position {i + 1}"
        mode = mode_by_name.get(outfit.get("label"))
        mode_desc = f"\nMode: {mode['description']}" if mode else ""
        blocks.append(
            f"Outfit to fix: {label}{mode_desc}\n"
            f"Previous attempt: {json.dumps(outfit, ensure_ascii=False)}\n"
            "Violations:\n" + "\n".join(f"- {msg}" for msg in violations)
        )
    blocks.append("Wardrobe inventory (JSON):")
    blocks.append(json.dumps(wardrobe, ensure_ascii=False))

    try:
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
            messages=[{"role": "user", "content": "\n\n".join(blocks)}],
        )
        repaired = parse_json(resp).get("outfits", [])
    except Exception:
        log.warning("outfit repair call failed; will retry or fall back", exc_info=True)
        return [None] * len(failed)
    return repaired + [None] * (len(failed) - len(repaired))


def parse_json(resp) -> dict:
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.startswith("json"):
            text = text[4:]
        text = text.strip("` \n")
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        stop_reason = getattr(resp, "stop_reason", None)
        preview = text[:500]
        suffix = text[-500:]
        raise ValueError(
            "Claude returned invalid JSON"
            f" (stop_reason={stop_reason}, length={len(text)}): {e}. "
            f"Start: {preview!r}. End: {suffix!r}"
        ) from e
