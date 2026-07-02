"""Weekly preference-inference job — distill outfit verdicts into editable
inferred preferences (#62).

The second LangGraph in the codebase (after services/trip_planner.py), chosen
deliberately: unlike the daily path, **a failed weekly run costs nothing**, so
this is the low-risk place to take LangGraph reps. The graph:

    fetch ──> check_evidence ──(enough)──> infer ──> validate ──> upsert ──> END
                              └──(too few)──────────────────────────────────> END

What it produces: rows in the `preferences` table with source = 'inferred',
each a short style statement citing the `outfit_history` rows that back it
(`evidence_ids`). Those rows flow into every future generation prompt for free
— recommend._get_active_preferences() selects status = 'active' regardless of
source — and render in the profile UI (#61) where they can be edited (promotes
to source = 'user', this job never touches it again) or dismissed (status =
'rejected', a tombstone this job must not re-emit).

Four load-bearing guardrails from the issue, and where each lives:
  1. Inferred prefs must be LEGIBLE — short, specific, evidence-cited. The
     editable UI is the only floor against a wrong inference becoming a
     systematic bias (the numeric loop self-corrects; injected prose doesn't),
     so evidence_ids are mandatory. → the prompt + validate_node.
  2. "Insufficient evidence" is a valid output. → MIN_VERDICTS hard floor
     (check_evidence) AND the model is told an empty list is success.
  3. Re-derive, don't append — regenerate the whole inferred set each run.
     → upsert_node replaces the prior active-inferred set.
  4. Promote-on-edit, never overwrite — anything the user authored or edited is
     hers. → this job only ever reads source='user' rows; it writes and deletes
     only source='inferred', status='active' rows. The router enforces the
     promotion/tombstone transitions (tested in tests/test_preferences.py).

Atomicity note (PostgREST gives no transaction): upsert INSERTS the fresh set
first, then deletes the prior ids — so a mid-run failure leaves a stale-but-
present set, never an empty one. And the graph only reaches upsert if the
Claude call and JSON parse both succeeded; a failed inference aborts with the
table untouched. See D8 in docs/feedback-loop-design.md.
"""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import TypedDict

from db.supabase import client as supabase
from langgraph.graph import END, StateGraph
from services.claude import client, parse_json

log = logging.getLogger("wardrobe.preference_inference")

MODEL = "claude-sonnet-4-6"

# Hard cold-start floor: don't infer anything until at least this many verdicts
# exist across all history. Verdicts accumulate (the input only grows), so this
# really only guards the first week or two. The model is the real arbiter past
# this point. ~10-20 verdicts/week is "tea-leaf territory" per the issue.
MIN_VERDICTS = 10

# A preference backed by one or two outfits is noise, not a pattern. Each
# emitted statement must cite at least this many distinct verdict rows.
MIN_EVIDENCE_PER_STATEMENT = 3

# DB constraint on preferences.text is 1-500 chars; statements should be far
# shorter, but we only enforce the hard DB bound here and lean on the prompt
# for brevity (dropping a slightly-long-but-correct statement loses signal).
MAX_STATEMENT_LEN = 500


class InferenceState(TypedDict, total=False):
    # filled by fetch_node
    verdicts: list[dict]  # shaped verdict rows, newest first; index = position
    existing_user: list[str]  # active user-authored pref texts (context only)
    existing_rejected: list[str]  # rejected inferred texts (do-not-re-emit)
    prior_inferred_ids: list[str]  # active inferred row ids to delete after insert

    # filled by infer_node, refined by validate_node
    inferred: list[dict]  # [{text, evidence_ids}]
    written: int  # how many rows upsert wrote (for logging/return)


# ---------------------------------------------------------------------------
# Nodes
# ---------------------------------------------------------------------------


def fetch_node(state: InferenceState) -> dict:
    """Pull the full verdict history + the three existing preference sets.

    Verdicts: every outfit_history row carrying a ±1 verdict (no window —
    taste is global, same reasoning as outfit_history._feedback_rows), with
    item names hydrated and the recommendation-time context (#60: attribution,
    weather, notes) that lets the model reason about *why* a verdict landed.

    Preferences are partitioned here rather than via the router (which only
    exposes active rows): the job needs the rejected tombstones too.
    """
    rows = (
        supabase()
        .table("outfit_history")
        .select(
            "id, recommended_on, mode, item_ids, feedback,"
            " feedback_reason, feedback_item_ids, feedback_note, weather, notes"
        )
        .not_.is_("feedback", "null")
        .order("recommended_on", desc=True)
        .execute()
        .data
        or []
    )

    item_ids = sorted({iid for r in rows for iid in (r.get("item_ids") or [])})
    names: dict[str, str] = {}
    if item_ids:
        res = (
            supabase()
            .table("clothing_items")
            .select("id, name")
            .in_("id", item_ids)
            .execute()
        )
        names = {r["id"]: r["name"] for r in (res.data or [])}

    prefs = (
        supabase()
        .table("preferences")
        .select("id, text, source, status")
        .execute()
        .data
        or []
    )

    return {
        "verdicts": _shape_verdicts(rows, names),
        "existing_user": [
            p["text"]
            for p in prefs
            if p["source"] == "user" and p["status"] == "active"
        ],
        "existing_rejected": [
            p["text"]
            for p in prefs
            if p["source"] == "inferred" and p["status"] == "rejected"
        ],
        "prior_inferred_ids": [
            p["id"]
            for p in prefs
            if p["source"] == "inferred" and p["status"] == "active"
        ],
    }


def check_evidence(state: InferenceState) -> str:
    """Router: gate the whole inference on a minimum verdict count.

    Returns to END without touching the table when below the floor — a
    cold-start run must NOT wipe whatever inferred set already exists.
    """
    n = len(state.get("verdicts", []))
    if n < MIN_VERDICTS:
        log.info(
            "insufficient evidence: %d verdict(s) < MIN_VERDICTS=%d; "
            "leaving inferred preferences untouched",
            n,
            MIN_VERDICTS,
        )
        return "insufficient"
    return "sufficient"


def infer_node(state: InferenceState) -> dict:
    """One Claude call: verdict history → candidate preference statements.

    Raises on API/parse failure — the graph never reaches upsert_node, so a
    failed inference leaves the table exactly as it was (guardrail 2 covers
    *empty* output, not *failed* output; conflating them is how a crash wipes
    the user's prefs).
    """
    inferred = infer_preferences(
        state["verdicts"],
        state.get("existing_user", []),
        state.get("existing_rejected", []),
    )
    return {"inferred": inferred}


def validate_node(state: InferenceState) -> dict:
    """Map cited indices → real outfit_history ids and drop weak/blocked ones.

    Defense in depth: the model is *told* the evidence floor and the rejected
    list, but we enforce both here so a sloppy or rephrasing model can't (a)
    emit a single-data-point preference or (b) resurrect a dismissed one.
    """
    validated = _validate_inferred(
        state.get("inferred", []),
        verdicts=state.get("verdicts", []),
        rejected=state.get("existing_rejected", []),
        existing_user=state.get("existing_user", []),
    )
    return {"inferred": validated}


def upsert_node(state: InferenceState) -> dict:
    """Re-derive the inferred set: INSERT fresh, then delete the prior ids.

    Insert-then-delete (not delete-then-insert) is the only atomicity lever
    PostgREST gives us: a failure between the two leaves duplicates that next
    week's run cleans up (it captures *all* active-inferred ids as prior), but
    never an empty set. The genuine empty case — model returned [] on growing
    data — is a real wipe, which is correct re-derivation but should be rare;
    we log it loudly because nonempty→empty on *more* evidence is a red flag.
    """
    inferred = state.get("inferred", [])
    prior_ids = state.get("prior_inferred_ids", [])

    if not inferred and prior_ids:
        log.warning(
            "inference produced 0 preferences while %d inferred pref(s) exist; "
            "re-deriving to empty — verify this isn't a prompt/parse regression",
            len(prior_ids),
        )

    rows = [
        {
            "text": p["text"],
            "source": "inferred",
            "status": "active",
            "evidence_ids": p["evidence_ids"],
        }
        for p in inferred
    ]
    if rows:
        supabase().table("preferences").insert(rows).execute()
    if prior_ids:
        supabase().table("preferences").delete().in_("id", prior_ids).execute()

    log.info(
        "inferred preferences re-derived: wrote %d, removed %d prior",
        len(rows),
        len(prior_ids),
    )
    return {"written": len(rows)}


# ---------------------------------------------------------------------------
# Pure helpers (unit-tested in tests/test_preference_inference.py)
# ---------------------------------------------------------------------------


def _shape_verdicts(rows: list[dict], names_by_id: dict[str, str]) -> list[dict]:
    """Pure: outfit_history rows → compact verdict dicts the prompt renders.

    Non-±1 verdicts are skipped defensively (same as the sampler). Deleted
    items drop out of item_names silently; a verdict whose items are all gone
    still carries mode/weather/note signal, so it's kept. Order is preserved
    (caller passes newest-first), because the prompt cites by 1-based index.
    """
    shaped = []
    for row in rows:
        verdict = row.get("feedback")
        if verdict not in (1, -1):
            continue
        item_ids = row.get("item_ids") or []
        shaped.append(
            {
                "id": row["id"],
                "date": row.get("recommended_on"),
                "mode": row.get("mode"),
                "verdict": verdict,
                "item_names": [names_by_id[i] for i in item_ids if i in names_by_id],
                "reason": row.get("feedback_reason"),
                "note": (row.get("feedback_note") or "").strip() or None,
                "weather": row.get("weather"),
            }
        )
    return shaped


def _validate_inferred(
    inferred: list[dict],
    verdicts: list[dict],
    rejected: list[str],
    existing_user: list[str],
) -> list[dict]:
    """Pure: turn raw model output into write-ready {text, evidence_ids} rows.

    Per candidate: coerce the cited 1-based indices to real verdict ids
    (unknown indices dropped), require >= MIN_EVIDENCE_PER_STATEMENT distinct
    ids, require a non-empty in-bounds text, and drop any whose normalized text
    collides with a rejected tombstone or an existing user pref. The tombstone
    guard is best-effort — normalized exact match catches restatements, not
    clever paraphrases (the editable UI is the backstop for those).
    """
    id_by_index = {i + 1: v["id"] for i, v in enumerate(verdicts)}
    blocked = {_normalize(t) for t in rejected} | {_normalize(t) for t in existing_user}

    out: list[dict] = []
    for cand in inferred:
        text = (cand.get("text") or "").strip()
        if not (1 <= len(text) <= MAX_STATEMENT_LEN):
            continue
        if _normalize(text) in blocked:
            log.info("dropping inferred pref (rejected/duplicate): %r", text)
            continue
        evidence_ids: list[str] = []
        for raw in cand.get("evidence", []) or []:
            try:
                idx = int(raw)
            except (TypeError, ValueError):
                continue
            rid = id_by_index.get(idx)
            if rid and rid not in evidence_ids:
                evidence_ids.append(rid)
        if len(evidence_ids) < MIN_EVIDENCE_PER_STATEMENT:
            log.info(
                "dropping inferred pref (%d < %d evidence): %r",
                len(evidence_ids),
                MIN_EVIDENCE_PER_STATEMENT,
                text,
            )
            continue
        out.append({"text": text, "evidence_ids": evidence_ids})
    return out


def _normalize(text: str) -> str:
    """Casefold + collapse whitespace + strip trailing punctuation, for the
    best-effort dedup/tombstone match. Not semantic — a paraphrase slips past."""
    return re.sub(r"\s+", " ", (text or "").strip().casefold()).rstrip(".!,;: ")


def _weather_phrase(weather: dict | None) -> str:
    """Pure: the recommendation-time weather as one compact clause, or ''.

    Same dict shape recommend() logs (temp_high_c/temp_low_c/conditions). Best
    effort: a missing or malformed blob just yields no weather clause."""
    if not isinstance(weather, dict):
        return ""
    hi, lo = weather.get("temp_high_c"), weather.get("temp_low_c")
    cond = (weather.get("conditions") or "").strip()
    parts = []
    if hi is not None and lo is not None:
        parts.append(f"{hi}/{lo}°C")
    if cond:
        parts.append(cond)
    return ", ".join(parts)


def _verdict_line(index: int, v: dict) -> str:
    """Pure: render one verdict as a single citeable line, prefixed [index]."""
    thumb = "👍 liked" if v["verdict"] == 1 else "👎 disliked"
    bits = [f"[{index}]", thumb]
    if v.get("date"):
        bits.append(str(v["date"]))
    if v.get("mode"):
        bits.append(f"· {v['mode']}")
    items = " + ".join(v.get("item_names") or []) or "(items no longer in catalog)"
    bits.append(f"· {items}")
    if v.get("reason"):
        bits.append(f"· reason: {v['reason']}")
    weather = _weather_phrase(v.get("weather"))
    if weather:
        bits.append(f"· weather: {weather}")
    line = " ".join(bits)
    if v.get("note"):
        line += f'\n      note: "{v["note"]}"'
    return line


PREFERENCE_INFERENCE_SYSTEM_PROMPT = """You distill a person's outfit feedback \
into a short list of durable STYLE PREFERENCES.

You are given her thumbs-up / thumbs-down verdicts on outfits an app recommended \
her, newest first. Each verdict line is numbered [N] and may carry the reason she \
gave, the weather that day, and a free-text note. Your job is to find the patterns \
that explain WHY outfits landed well or badly, and state them as preferences she \
could read and recognize as her own taste.

Hard rules:
- Capture BOTH polarities — what she consistently likes ("Likes monochrome looks \
for elevated occasions") as well as what she avoids ("Dislikes sporty footwear \
with dressy outfits"). Do not only emit avoid-statements.
- Each preference must be SHORT and SPECIFIC — one sentence, a concrete pattern, \
phrased as her standing taste, not a description of one outfit.
- Each preference must be backed by at least THREE distinct verdict lines that \
genuinely show the pattern. Cite them by their [N] numbers in `evidence`. A \
pattern you can only support with one or two outfits is noise — do not emit it.
- Do NOT restate a preference she already wrote (listed under "Already known"). \
Do NOT re-emit or paraphrase one she previously dismissed (listed under \
"Previously dismissed"). She rejected those on purpose.
- Weather-attributed dislikes are feedback on the forecast call, not her taste — \
do not turn them into style preferences.
- An EMPTY list is a correct, expected answer. If the verdicts don't yet show a \
clear, repeated pattern, return no preferences. Never invent one to fill space — \
a wrong inference biases every future outfit she gets.

Return ONLY a JSON object of this shape:

{
  "preferences": [
    {"text": "Dislikes sporty footwear with elevated outfits", "evidence": [2, 5, 9]},
    {"text": "Likes earth-tone layering on cold days", "evidence": [1, 4, 7, 8]}
  ]
}

No commentary, no markdown fences. The JSON must be parseable. `preferences` may \
be an empty array.
"""


def _build_inference_prompt(
    verdicts: list[dict],
    existing_user: list[str],
    rejected: list[str],
) -> str:
    """Pure: assemble the user message. Verdicts numbered 1..N in list order so
    the model's `evidence` indices map back by position in validate_node."""
    blocks = [
        "Outfit verdicts (newest first). Cite these by their [N] number:",
        "\n".join(_verdict_line(i + 1, v) for i, v in enumerate(verdicts)),
    ]
    if existing_user:
        blocks.append(
            "Already known — preferences she has written herself; do NOT restate "
            "these:\n" + "\n".join(f"- {t}" for t in existing_user)
        )
    if rejected:
        blocks.append(
            "Previously dismissed — inferences she rejected; do NOT re-emit or "
            "paraphrase these:\n" + "\n".join(f"- {t}" for t in rejected)
        )
    blocks.append(
        "Return the preferences JSON. Remember: both polarities, >=3 evidence "
        "citations each, and an empty list if no clear pattern has formed yet."
    )
    return "\n\n".join(blocks)


def infer_preferences(
    verdicts: list[dict],
    existing_user: list[str],
    rejected: list[str],
) -> list[dict]:
    """Call the model and return its raw candidate list ([{text, evidence}]).

    Index→id mapping and all filtering happen later in validate_node; this just
    surfaces what the model proposed. Raises on API/parse error by design."""
    resp = client().messages.create(
        model=MODEL,
        max_tokens=2048,
        system=[
            {
                "type": "text",
                "text": PREFERENCE_INFERENCE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": _build_inference_prompt(verdicts, existing_user, rejected),
            }
        ],
    )
    parsed = parse_json(resp)
    candidates = parsed.get("preferences", [])
    return [c for c in candidates if isinstance(c, dict)]


# ---------------------------------------------------------------------------
# Graph
# ---------------------------------------------------------------------------


def build_graph():
    g = StateGraph(InferenceState)

    g.add_node("fetch", fetch_node)
    g.add_node("infer", infer_node)
    g.add_node("validate", validate_node)
    g.add_node("upsert", upsert_node)

    g.set_entry_point("fetch")
    g.add_conditional_edges(
        "fetch",
        check_evidence,
        {"sufficient": "infer", "insufficient": END},
    )
    g.add_edge("infer", "validate")
    g.add_edge("validate", "upsert")
    g.add_edge("upsert", END)

    return g.compile()


# Compiled once at module load and reused, same as trip_planner._APP.
_APP = build_graph()


def _record_reviewed() -> None:
    """Stamp profile.preferences_reviewed_at = now() — the job's heartbeat (#62).

    Written only after a fully successful graph run (run() reaches this line
    only if _APP.invoke didn't raise), so the value goes stale on any failure
    and the Profile UI's "reviewed N days ago" becomes the alarm. Upserts the
    single profile row the same way PUT /profile does — create if missing, so a
    user who never set a home location still gets a heartbeat.
    """
    now = datetime.now(timezone.utc).isoformat()
    existing = supabase().table("profile").select("id").limit(1).execute()
    if existing.data:
        supabase().table("profile").update({"preferences_reviewed_at": now}).eq(
            "id", existing.data[0]["id"]
        ).execute()
    else:
        supabase().table("profile").insert({"preferences_reviewed_at": now}).execute()


def run() -> dict:
    """Run the weekly inference graph. Returns a small summary dict.

    On insufficient evidence the graph short-circuits to END and `written` is
    absent — the caller (jobs/infer_preferences.py) treats that as a no-op
    success. Any exception from the Claude call propagates so the job can exit
    nonzero with the table untouched.

    A clean return — for ANY healthy outcome (wrote prefs, found none, or too
    little evidence) — stamps the heartbeat last, so a failure is the only thing
    that leaves it stale."""
    final = _APP.invoke({})
    _record_reviewed()
    return {
        "verdicts": len(final.get("verdicts", [])),
        "written": final.get("written"),
        "inferred": final.get("inferred", []),
    }
