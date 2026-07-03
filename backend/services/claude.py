import base64
import json
import logging
import os
import re
from functools import lru_cache

from anthropic import Anthropic

from observability import op
from services.image import ensure_under_limit
from services.validation import drop_extras, validate_outfit

log = logging.getLogger("wardrobe.claude")

MODEL = "claude-sonnet-4-6"

# Calendar → modes classification (#64) is a tiny once-a-day call; a
# Haiku-class model is plenty and keeps the job cheap.
MODE_CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"

# Outfit structural repair (issue #46): how many targeted re-asks before the
# deterministic drop_extras fallback kicks in.
MAX_REPAIR_ATTEMPTS = 2

# Two-stage lite (#63): candidates requested per outfit entry. The value is
# baked into OUTFIT_SYSTEM_PROMPT as a literal "3" — change both together
# (the system prompt must stay byte-identical for its cache_control prefix).
CANDIDATES_PER_OUTFIT = 3

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

# Shared between the single-item and multi-item tagging prompts (#24) so the
# per-item field spec can't drift between them.
TAGGING_FIELD_SPEC = f"""\
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
  return null. Do not guess."""

TAGGING_SYSTEM_PROMPT = f"""You are a clothing-tagging assistant for a personal wardrobe app.

Given a photo that may contain one clothing/accessory item, return a JSON object
of the shape:

{{"items": [<one tag object>]}}

The tag object has these fields:

{TAGGING_FIELD_SPEC}

Return ONLY the JSON object, no commentary, no markdown fences. The JSON must
be parseable. If multiple items appear in the photo, tag only the most
prominent one. If the photo contains no clothing or accessory items, return
{{"items": []}}.
"""

# Multi-item tagging (#24): hard cap on items per photo. Baked into the prompt
# as a literal "9" and enforced defensively after parsing.
MAX_MULTI_ITEMS = 9

TAGGING_MULTI_SYSTEM_PROMPT = f"""You are a clothing-tagging assistant for a personal wardrobe app.

Given a photo containing one or more clothing/accessory items (e.g. jewelry on
a tray, several hair clips, a pile of scarves), enumerate every distinct item
and return a JSON object of the shape:

{{"items": [<one tag object per item>, ...]}}

Each tag object has these fields:

{TAGGING_FIELD_SPEC}

Rules:
- One tag object per distinct physical item. Do not merge similar items; two
  near-identical hair clips are two entries.
- Keep each description to 1-2 sentences.
- Tag at most 9 items. If the photo has more, tag the 9 most prominent.
- If the photo contains no clothing or accessory items, return {{"items": []}}.

Return ONLY the JSON object, no commentary, no markdown fences. The JSON must
be parseable.
"""


@lru_cache(maxsize=1)
def client() -> Anthropic:
    return Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def tag_clothing_photo(image_bytes: bytes, mime_type: str) -> dict | None:
    """Send photo to Claude vision; return parsed tag dict or None.

    Uses prompt caching on the system prompt so repeat tagging is cheaper.
    None means Claude found no clothing/accessory item in the photo.
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

    items = _tag_items_from_response(parse_json(resp))
    return items[0] if items else None


@op  # Weave trace node (#85); the Anthropic call inside auto-nests here.
def tag_clothing_photo_multi(image_bytes: bytes, mime_type: str) -> list[dict]:
    """Send photo to Claude vision; return one parsed tag dict per item found.

    Multi-item variant of tag_clothing_photo (#24). Returns [] when Claude
    finds no clothing/accessory items, and at most MAX_MULTI_ITEMS entries.
    """
    image_bytes, mime_type = ensure_under_limit(image_bytes, mime_type)
    image_b64 = base64.standard_b64encode(image_bytes).decode("ascii")

    resp = client().messages.create(
        model=MODEL,
        # Up to 9 items per photo; the single-item 512 budget would truncate
        # mid-JSON and fail the whole upload.
        max_tokens=4096,
        system=[
            {
                "type": "text",
                "text": TAGGING_MULTI_SYSTEM_PROMPT,
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
                    {"type": "text", "text": "Tag every item in this photo."},
                ],
            }
        ],
    )

    items = _tag_items_from_response(parse_json(resp))
    return items[:MAX_MULTI_ITEMS]


def _tag_items_from_response(data) -> list[dict]:
    """Normalize single/multi tagging JSON into a list of tag objects."""

    # Tolerate a bare array even though the prompt asks for {"items": [...]}.
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and "items" in data:
        items = data["items"]
    elif isinstance(data, dict):
        # Backward compatibility for older single-item responses that emitted
        # the tag object directly.
        items = [data]
    else:
        raise ValueError(f"Expected a JSON object or array, got {type(data).__name__}")
    if not isinstance(items, list):
        raise ValueError(f"Expected a list of tag objects, got {type(items).__name__}")
    return items


MODE_CLASSIFIER_PROMPT = """You select which outfit "modes" a day's plans call
for. Given today's calendar events (titles and times) and the available modes
with descriptions, return ONLY a JSON object:
{"modes": ["<mode name>", ...],
 "explanation": "<1-2 sentences, addressed to the user>"}

Include a mode only when an event clearly calls for it — a workout class calls
for an athletic mode; a dinner reservation, date, or event calls for a dressier
mode. Routine events (errands, calls, appointments) that don't change what to
wear should not add modes. Use the exact mode names given. An empty list is a
valid answer.

The explanation appears in the user's morning email: in 1-2 friendly
sentences, say what you see on today's calendar and why it does (or doesn't)
call for extra modes — e.g. "We see solidcore at 9:00 AM, so Athleisure is
recommended alongside the default Smart casual." No commentary outside the
JSON, no markdown fences."""


def classify_modes(
    events: list[dict], modes: list[dict], floor: str | None = None
) -> tuple[list[str], str]:
    """One Haiku-class call: today's calendar events → applicable modes (#64).

    Returns (raw mode-name strings, user-facing explanation for the email).
    The caller (services.calendar) validates the names against the known
    list, always re-adds the floor mode, and treats any exception as "fall
    back to all modes" — so this function can just raise. Keyword rules were
    considered and rejected in the issue: titles drift ("PT session",
    "Dinner @ Quince") and a keyword list goes stale silently.
    """
    blocks = [
        "Today's calendar events:",
        *[f"- {e['title']} ({e['time']})" for e in events],
        "",
        "Available modes:",
        *[f"- {m['name']}: {m['description']}" for m in modes],
    ]
    if floor:
        blocks += [
            "",
            f'Note: "{floor}" is always included as the default mode — present '
            "any other modes in the explanation as additions to it.",
        ]
    resp = client().messages.create(
        model=MODE_CLASSIFIER_MODEL,
        max_tokens=512,
        system=MODE_CLASSIFIER_PROMPT,
        messages=[{"role": "user", "content": "\n".join(blocks)}],
    )
    parsed = parse_json(resp)
    names = [str(name) for name in parsed.get("modes", [])]
    explanation = str(parsed.get("explanation") or "").strip()
    return names, explanation


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
- The user message may include a "User preferences" section listing explicit
  style statements the user wrote herself. Treat each as a hard constraint —
  honor it in every outfit, and if you cannot, briefly acknowledge it in that
  outfit's reasoning.
- The user message may also include a "Learned preferences" section: patterns
  inferred from the user's past thumbs feedback. Treat these as SOFT — lean
  toward them when choosing between otherwise comparable options, but they are
  guesses that may be wrong. Do NOT force them, do NOT sacrifice
  weather-appropriateness or coherence for them, and never skip a mode or
  acknowledge them in `reasoning` on their account. A hard "User preference"
  always wins over a "Learned preference" if the two ever conflict.

If the user provides a list of MODES, return exactly one outfit entry per mode
in the SAME ORDER. Each entry must fit the mode's vibe. Repeat the mode name in
the entry's `label` field. If no modes are provided, set `label` to an empty
string and return the requested number of entries.

For each entry, propose 3 CANDIDATE outfits, ordered best-first. Candidates
must differ meaningfully from each other — different anchor pieces, not the
same outfit with one accessory swapped. Every candidate must independently
satisfy ALL the rules above, including the slot-omission rule: a candidate
that notes a gap in its `reasoning` must actually omit that slot from its
`item_ids`.

If no suitable outfit can be assembled for a given mode under today's weather
(e.g. the wardrobe lacks elevated pieces, or every option would be wildly
inappropriate for the conditions), DO NOT force a bad suggestion. Instead,
return the entry with a SINGLE candidate whose `item_ids` is [] and whose
`reasoning` begins with "No <mode-name> recommendation available today" and
explains why in one sentence. Keep the entry in the same position; do not drop
modes. When you skip a mode this way, `item_ids` MUST be the empty list —
never combine the "No … recommendation available today" reasoning with
non-empty item_ids.

Return ONLY a JSON object of the shape:
{
  "outfits": [
    {
      "label": "<mode name or empty string>",
      "candidates": [
        {"item_ids": ["<uuid>", "<uuid>", ...], "reasoning": "1-2 sentences"},
        {"item_ids": ["<uuid>", "<uuid>", ...], "reasoning": "1-2 sentences"},
        {"item_ids": ["<uuid>", "<uuid>", ...], "reasoning": "1-2 sentences"}
      ]
    },
    ...
  ]
}

No commentary, no markdown fences. The JSON must be parseable.
"""


@op  # Weave trace node (#85); the Anthropic call inside auto-nests here.
def recommend_outfits(
    weather: dict,
    wardrobe: list[dict],
    n: int,
    notes: str = "",
    modes: list[dict] | None = None,
    feedback_entries: list[dict] | None = None,
    blocked_combos: set[frozenset[str]] | None = None,
    recent_combos: set[frozenset[str]] | None = None,
    preferences: list[str] | None = None,
    inferred_preferences: list[str] | None = None,
) -> list[dict]:
    """Ask Claude for outfit suggestions. Returns list of {label, item_ids, reasoning}.

    If `modes` is provided, returns one outfit per mode in order; `n` is ignored.
    Each mode is a dict with keys `name` and `description`.

    `feedback_entries` (from outfit_history.recent_feedback_outfits, #59) is
    rendered into the user message — NOT the system prompt, which must stay
    byte-identical to keep its cache_control prefix valid across calls.

    Two-stage lite (#63): the single call returns CANDIDATES_PER_OUTFIT
    candidates per entry; deterministic selection (_select_candidates) takes
    the first candidate that isn't a 👎-attributed combination
    (`blocked_combos`, from outfit_history.blocked_combos), isn't an exact
    repeat of a recently recommended set (`recent_combos`, #17), and passes
    structural validation. _enforce_structure then only has to repair entries
    where no candidate survived.
    """
    user_blocks = [_weather_line(weather)]
    if modes:
        user_blocks.append("Modes (return one outfit entry per mode, in this order):")
        for m in modes:
            user_blocks.append(f"- {m['name']}: {m['description']}")
    else:
        user_blocks.append(
            f"Please return exactly {n} outfit entr{'ies' if n != 1 else 'y'}."
        )
    if notes.strip():
        user_blocks.append(f"User notes for today: {notes.strip()}")
    if feedback_entries:
        user_blocks.append(_feedback_block(feedback_entries))
    if preferences:
        user_blocks.append(_preferences_block(preferences))
    if inferred_preferences:
        user_blocks.append(_inferred_preferences_block(inferred_preferences))
    user_blocks.append("Wardrobe inventory (JSON):")
    user_blocks.append(json.dumps(wardrobe, ensure_ascii=False))

    resp = client().messages.create(
        model=MODEL,
        # 3 candidates per entry ≈ 3× the old payload; headroom keeps
        # parse_json's stop_reason=max_tokens diagnostics a rarity.
        max_tokens=4096,
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
    entries = _normalize_entries(parsed.get("outfits", []))
    types_by_id = {item["id"]: item.get("type", "") for item in wardrobe}
    outfits = _select_candidates(
        entries,
        blocked_combos or set(),
        types_by_id,
        recent_combos=recent_combos or set(),
    )
    return _enforce_structure(outfits, wardrobe, weather, modes, notes)


def _normalize_entries(outfits: list[dict]) -> list[dict]:
    """Pure: coerce each model entry to {label, candidates: [...]}.

    Tolerates the pre-#63 flat shape ({label, item_ids, reasoning}) by
    wrapping it as a single candidate — repair responses and stubborn models
    both produce it.
    """
    entries = []
    for o in outfits:
        if "candidates" in o:
            candidates = [c for c in (o.get("candidates") or []) if isinstance(c, dict)]
        else:
            candidates = [
                {"item_ids": o.get("item_ids", []), "reasoning": o.get("reasoning", "")}
            ]
        entries.append({"label": o.get("label", ""), "candidates": candidates})
    return entries


def _select_candidates(
    entries: list[dict],
    blocked_combos: set[frozenset[str]],
    types_by_id: dict[str, str],
    recent_combos: set[frozenset[str]] | None = None,
) -> list[dict]:
    """Pure-ish (logs): stage 2 of the two-stage lite (#63).

    Per entry, take the first candidate that (1) is not a 👎-attributed
    combination — a recorded fact, so it's enforced in code, not prose —
    (2) is not an exact repeat of a recently recommended set (#17), and
    (3) passes structural validation (#46). Every rejection is logged with
    its exact reason. Fallbacks, in severity order: a non-blocked but
    structurally invalid candidate (the existing repair machinery downstream
    fixes it — a fresh outfit needing repair beats a repeat); then a repeat
    (a repeated outfit beats an empty slot); only if *every* candidate is a
    👎-blocked combo, a skip entry — serving a known-bad outfit would defeat
    the filter, and the skip phrasing matches what _is_skip / the email
    template already handle.
    """
    recent_combos = recent_combos or set()
    picked = []
    for i, entry in enumerate(entries):
        label = entry.get("label") or f"entry {i + 1}"
        chosen = None
        repairable = None
        repeat = None
        for j, cand in enumerate(entry["candidates"]):
            item_ids = cand.get("item_ids") or []
            if item_ids and frozenset(item_ids) in blocked_combos:
                log.info(
                    "candidate %d/%d rejected [%s]: matches a 👎-attributed combination",
                    j + 1,
                    len(entry["candidates"]),
                    label,
                )
                continue
            if item_ids and frozenset(item_ids) in recent_combos:
                log.info(
                    "candidate %d/%d rejected [%s]: exact repeat of a recently "
                    "recommended outfit",
                    j + 1,
                    len(entry["candidates"]),
                    label,
                )
                repeat = repeat or cand
                continue
            violations = validate_outfit(item_ids, types_by_id)
            if violations:
                log.info(
                    "candidate %d/%d rejected [%s]: structural: %s",
                    j + 1,
                    len(entry["candidates"]),
                    label,
                    ", ".join(violations),
                )
                repairable = repairable or cand
                continue
            if j:
                log.info(
                    "selected candidate %d/%d for [%s]",
                    j + 1,
                    len(entry["candidates"]),
                    label,
                )
            chosen = cand
            break
        if chosen is None:
            chosen = repairable
        if chosen is None and repeat is not None:
            log.warning(
                "all candidates for [%s] were 👎-blocked or recent repeats; "
                "serving a repeat — better than an empty slot",
                label,
            )
            chosen = repeat
        if chosen is None:
            log.warning(
                "all candidates for [%s] matched 👎-attributed combinations; skipping",
                label,
            )
            chosen = {
                "item_ids": [],
                "reasoning": (
                    f"No {entry.get('label') or 'outfit'} recommendation available "
                    "today — every candidate repeated a combination you previously "
                    "disliked."
                ),
            }
        picked.append(
            {
                "label": entry.get("label", ""),
                "item_ids": chosen.get("item_ids", []),
                "reasoning": chosen.get("reasoning", ""),
            }
        )
    return picked


def _preferences_block(preferences: list[str]) -> str:
    """Pure: render user-authored preferences (#61) as the prompt section the
    system prompt's HARD-constraint bullet refers to. Empty list → empty string.
    """
    if not preferences:
        return ""
    return "User preferences:\n" + "\n".join(f"- {p}" for p in preferences)


def _inferred_preferences_block(preferences: list[str]) -> str:
    """Pure: render inferred preferences (#62) as the prompt section the
    system prompt's SOFT-preference bullet refers to.

    A separate block from _preferences_block on purpose: inferred prefs are a
    weekly job's guess from past feedback, so they nudge rather than bind, and
    a hard user pref outranks them on conflict. Empty list → empty string.
    """
    if not preferences:
        return ""
    return "Learned preferences:\n" + "\n".join(f"- {p}" for p in preferences)


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
        "corrected versions of ONLY the outfits listed below, in this order, as "
        '{"outfits": [{"label": ..., "item_ids": [...], "reasoning": ...}, ...]} '
        "— ONE corrected outfit per entry, no candidates array. Keep each "
        "outfit's label, fix the violations, and keep the outfit coherent for "
        "its mode and the weather.",
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
        # The system prompt teaches the candidates shape; if the model uses it
        # here despite the flat-shape instruction, take each entry's first.
        repaired = [
            {"label": e["label"], **e["candidates"][0]} if e["candidates"] else None
            for e in _normalize_entries(repaired)
        ]
    except Exception:
        log.warning("outfit repair call failed; will retry or fall back", exc_info=True)
        return [None] * len(failed)
    return repaired + [None] * (len(failed) - len(repaired))


_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL | re.IGNORECASE)


def _extract_json(text: str) -> str:
    """Best-effort isolate the JSON payload from a model response.

    Every prompt asks for raw JSON, but "return ONLY JSON" is a request, not a
    guarantee — a reasoning-capable model sometimes (a) wraps the object in a
    ```json fence or (b), seen on the weekly inference call (#62), narrates its
    analysis in prose first and emits the JSON at the end. Strategy: take the
    first fenced block if present, else the span from the first '{' to the last
    '}'. Falls back to the original text so parse_json's diagnostics still fire
    on genuinely unparseable (e.g. truncated) output. The happy path — a clean
    object with no wrapper — is unchanged: the span is the whole string.
    """
    fenced = _JSON_FENCE_RE.search(text)
    if fenced:
        return fenced.group(1).strip()
    if text.lstrip().startswith("["):
        # A response that *starts* with '[' is a bare top-level array (#24);
        # the brace-span heuristic below would mangle it into "{...}, {...}".
        # Only this unambiguous case — prose narration never starts with '['.
        start, end = text.find("["), text.rfind("]")
        if start < end:
            return text[start : end + 1]
    start, end = text.find("{"), text.rfind("}")
    if 0 <= start < end:
        return text[start : end + 1]
    return text


def parse_json(resp) -> dict:
    text = "".join(block.text for block in resp.content if block.type == "text").strip()
    try:
        return json.loads(_extract_json(text))
    except json.JSONDecodeError as e:
        stop_reason = getattr(resp, "stop_reason", None)
        preview = text[:500]
        suffix = text[-500:]
        raise ValueError(
            "Claude returned invalid JSON"
            f" (stop_reason={stop_reason}, length={len(text)}): {e}. "
            f"Start: {preview!r}. End: {suffix!r}"
        ) from e
