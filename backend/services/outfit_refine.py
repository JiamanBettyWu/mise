"""Multi-turn outfit refinement — the third production LangGraph (#145).

Design of record: docs/outfit-refinement-design.md. The learning payload is
the checkpointer: state is snapshotted per `thread_id` (= outfit_history row
id) after every step, so a later request with the same thread resumes the
conversation — candidate pool assembled once, turn history accumulating —
instead of starting fresh.

Graph:

    START → load_context → route ──(refine)────→ refine_outfit ──→ persist → END
                                  └─(regenerate)→ regenerate ────↗

The outfit_history row stays the source of truth for the *current* outfit
(persist writes it back each turn); the checkpointer carries only what has no
other home — the candidate pool and the conversation. In-memory MemorySaver
on purpose: a refinement chat is minutes long, Render runs one worker, and
losing it on a restart costs one re-generate (revisit with multi-user).
"""

import json
import logging
import operator
from datetime import date
from typing import Annotated, Literal, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from db.supabase import client as supabase
from observability import op
from services.claude import (
    MODE_CLASSIFIER_MODEL,
    MODEL,
    _weather_line,
    create_tracked,
    parse_json,
)
from services.modes import mode_by_name
from services.outfit_history import (
    blocked_combos,
    recent_combos,
    sample_wardrobe,
    update_outfit_items,
)
from services.recommend import WARDROBE_FIELDS, recommend
from services.validation import drop_extras, validate_outfit
from services.weather_gate import gate_extremes

log = logging.getLogger("wardrobe.refine")


class RefineState(TypedDict, total=False):
    # Row-derived, passed fresh on every invoke — the row is the source of
    # truth for the current outfit; the checkpointer never gets to disagree.
    history_id: str
    mode: str
    weather: dict
    notes: str
    current_item_ids: list[str]
    user_message: str
    # Checkpointer-carried: the conversation (operator.add appends each
    # invoke's [user_message]) and the pool assembled on the first turn.
    turns: Annotated[list[str], operator.add]
    candidate_pool: list[dict]
    # Per-turn outputs.
    route: str
    reasoning: str


ROUTE_SYSTEM_PROMPT = """You classify a user's follow-up message about a
recommended outfit into exactly one of two actions:

- "refine": the user wants targeted changes to this outfit — swap an item,
  adjust one slot, make it slightly warmer/dressier/more comfortable. The
  outfit's premise still holds.
- "regenerate": the day's constraints changed — a different activity, plan,
  occasion, or weather reality ("actually I'm biking today", "turns out I
  have a formal dinner") — so the outfit should be rebuilt from scratch.

Return ONLY a JSON object: {"route": "refine"} or {"route": "regenerate"}.
No commentary, no markdown fences."""


REFINE_SYSTEM_PROMPT = """You are a personal stylist refining an existing
outfit per the user's request. You will receive today's weather, the outfit
mode, a wardrobe inventory, the current outfit, and the conversation so far.

Rules:
- Change ONLY what the user's request requires; keep every other item.
- Replacements must come from the inventory; reference items by `id`.
- Stay weather-appropriate and coherent with the mode. Respect each item's
  `warmth` rating (1 minimal – 5 maximum; null = doesn't affect warmth).
- Keep at most ONE bottom (trousers, jeans, skirt, or shorts) and at most ONE
  pair of footwear.
- If the inventory has nothing suitable for the requested change, keep the
  outfit unchanged and say so briefly in `reasoning`.

Return ONLY a JSON object:
{"item_ids": ["<uuid>", ...], "reasoning": "1-2 sentences on what changed and why"}

No commentary, no markdown fences. The JSON must be parseable."""


def load_context_node(state: RefineState) -> dict:
    """First turn only: assemble the candidate pool for this conversation.

    Rebuilds rather than replays the original generation's pool (design doc:
    no change to the generate path) — weather comes from the row so the pool
    matches recommendation-time conditions, and the current outfit's items
    are force-included so "swap just the shoes" is always expressible even
    when sampling wouldn't have re-drawn them.
    """
    if state.get("candidate_pool"):
        return {}
    wardrobe = (
        supabase()
        .table("clothing_items")
        .select(WARDROBE_FIELDS)
        .eq("available", True)
        .execute()
        .data
        or []
    )
    wearable = gate_extremes(wardrobe, state["weather"])
    pool = sample_wardrobe(wearable, modes=[{"name": state["mode"]}])
    pooled = {item["id"] for item in pool}
    by_id = {item["id"] for item in wardrobe}
    for iid in state["current_item_ids"]:
        if iid not in pooled and iid in by_id:
            pool += [item for item in wardrobe if item["id"] == iid]
    log.info("refine pool for %s: %d items", state["history_id"], len(pool))
    return {"candidate_pool": pool}


def route_node(state: RefineState) -> dict:
    """Haiku classification: refine vs regenerate. Failure → refine (the
    cheaper, non-destructive branch), mirroring calendar.classify_modes'
    fail-open posture."""
    blocks = [
        f"Outfit mode: {state['mode']}",
        _weather_line(state["weather"]),
    ]
    prior = state.get("turns", [])[:-1]
    if prior:
        blocks.append(
            "Earlier refinement requests this conversation:\n"
            + "\n".join(f"- {t}" for t in prior)
        )
    blocks.append(f"User's new message: {state['user_message']}")
    try:
        resp = create_tracked(
            "outfit_refine_route",
            model=MODE_CLASSIFIER_MODEL,
            max_tokens=64,
            system=ROUTE_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "\n\n".join(blocks)}],
        )
        route = parse_json(resp).get("route")
        if route not in ("refine", "regenerate"):
            raise ValueError(f"unknown route {route!r}")
    except Exception:
        log.warning("route classification failed; defaulting to refine", exc_info=True)
        route = "refine"
    log.info("route for %s: %s", state["history_id"], route)
    return {"route": route}


def check_route(state: RefineState) -> Literal["refine", "regenerate"]:
    """Router function for the conditional edge — reads, never mutates."""
    return state["route"]


def refine_outfit_node(state: RefineState) -> dict:
    """Sonnet call: targeted changes only, then the same deterministic guards
    generation applies — 👎-attributed combinations (#60) and recent exact
    repeats (#17) are recorded facts, enforced in code, not prose."""
    pool = state["candidate_pool"]
    names_by_id = {item["id"]: item.get("name", "") for item in pool}
    current = [item for item in pool if item["id"] in set(state["current_item_ids"])]

    # Prompt is split at the turn-stable boundary (#154): weather, mode, and
    # the pool are identical across a conversation's turns (the checkpointer
    # carries the pool unchanged), so a cache breakpoint after them lets turn
    # 2+ reuse the big inventory JSON instead of re-reading it — the current
    # outfit and conversation, which change every turn, come after.
    stable = [
        _weather_line(state["weather"]),
        f"Outfit mode: {state['mode']}",
        "Wardrobe inventory (JSON):",
        json.dumps(pool, ensure_ascii=False),
    ]
    blocks = [
        "Current outfit (JSON):",
        json.dumps(current, ensure_ascii=False),
    ]
    prior = state.get("turns", [])[:-1]
    if prior:
        blocks.append(
            "Earlier refinement requests, already applied:\n"
            + "\n".join(f"- {t}" for t in prior)
        )
    if state.get("notes"):
        blocks.append(f"User notes from the original request: {state['notes']}")
    blocks.append(f"User's refinement request: {state['user_message']}")

    resp = create_tracked(
        "outfit_refine",
        model=MODEL,
        max_tokens=1024,
        system=[
            {
                "type": "text",
                "text": REFINE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": "\n\n".join(stable),
                        "cache_control": {"type": "ephemeral"},
                    },
                    {"type": "text", "text": "\n\n".join(blocks)},
                ],
            }
        ],
    )
    parsed = parse_json(resp)
    item_ids = [iid for iid in parsed.get("item_ids", []) if iid in names_by_id]
    reasoning = str(parsed.get("reasoning", "")).strip()

    combo = frozenset(item_ids)
    unchanged = combo == frozenset(state["current_item_ids"])
    if not unchanged and item_ids:
        if combo in blocked_combos():
            log.info("refined set for %s is a 👎-blocked combo", state["history_id"])
            return {
                "reasoning": "Kept the outfit unchanged — that swap would "
                "recreate a combination you previously disliked."
            }
        if combo in recent_combos():
            log.info("refined set for %s is a recent repeat", state["history_id"])
            return {
                "reasoning": "Kept the outfit unchanged — that swap would "
                "repeat an outfit from the past week."
            }
    types_by_id = {item["id"]: item.get("type", "") for item in pool}
    if validate_outfit(item_ids, types_by_id):
        item_ids = drop_extras(item_ids, types_by_id)
    if not item_ids:
        return {"reasoning": reasoning or "No suitable change found — outfit kept."}
    return {"current_item_ids": item_ids, "reasoning": reasoning}


def regenerate_node(state: RefineState) -> dict:
    """Constraints changed: rerun the full pipeline for this one mode with the
    conversation folded into `notes` (the #135 seam), reusing the row's
    weather. persist=False — our own persist node owns the row update.
    Resets the pool so the next turn's load_context rebuilds it against the
    new premise."""
    mode = mode_by_name(state["mode"])
    combined = "; ".join(
        part for part in [state.get("notes", ""), *state.get("turns", [])] if part
    )
    result = recommend(
        notes=combined,
        n=1,
        modes=[mode] if mode else None,
        persist=False,
        weather=state["weather"],
    )
    outfit = (result.get("outfits") or [{}])[0]
    item_ids = [item["id"] for item in outfit.get("items") or []]
    if not item_ids:
        return {
            "candidate_pool": [],
            "reasoning": outfit.get("reasoning")
            or "Couldn't rebuild the outfit — kept the current one.",
        }
    return {
        "candidate_pool": [],
        "current_item_ids": item_ids,
        "reasoning": outfit.get("reasoning", ""),
    }


def persist_node(state: RefineState) -> dict:
    """Write the accepted turn back to the row (final-version-only semantics;
    verdict cleared, config stamped refined) — shared helper with #144."""
    update_outfit_items(state["history_id"], state["current_item_ids"])
    return {}


def build_graph():
    g = StateGraph(RefineState)
    g.add_node("load_context", load_context_node)
    g.add_node("route", route_node)
    g.add_node("refine_outfit", refine_outfit_node)
    g.add_node("regenerate", regenerate_node)
    g.add_node("persist", persist_node)

    g.add_edge(START, "load_context")
    g.add_edge("load_context", "route")
    g.add_conditional_edges(
        "route",
        check_route,
        {"refine": "refine_outfit", "regenerate": "regenerate"},
    )
    g.add_edge("refine_outfit", "persist")
    g.add_edge("regenerate", "persist")
    g.add_edge("persist", END)
    return g.compile(checkpointer=MemorySaver())


# Compiled once at module load, like the trip planner's _APP. The MemorySaver
# lives inside it — one conversation store per process lifetime.
_APP = build_graph()


class RefineError(ValueError):
    """Invalid refine request. `.status` is the HTTP code."""

    def __init__(self, message: str, status: int):
        super().__init__(message)
        self.status = status


def _load_row(history_id: str, message: str) -> tuple[dict, str]:
    """Fetch + validate the target row. Shared by refine() and stream() so
    both entry points enforce the same guards, and stream() can raise them
    as HTTP errors BEFORE any SSE bytes go out."""
    message = (message or "").strip()
    if not message:
        raise RefineError("empty refinement message", 422)
    res = (
        supabase()
        .table("outfit_history")
        .select("id, recommended_on, mode, item_ids, weather, notes")
        .eq("id", history_id)
        .execute()
    )
    if not res.data:
        raise RefineError("outfit not found", 404)
    row = res.data[0]
    # Scope guard (design doc): today's generated outfits only, enforced
    # server-side — hiding the UI on historical rows is not a guard.
    if row["recommended_on"] != date.today().isoformat():
        raise RefineError("refinement is only available for today's outfits", 409)
    if not row.get("item_ids"):
        raise RefineError("nothing to refine — this outfit is empty", 409)
    if not row.get("weather"):
        raise RefineError("outfit has no recorded weather context", 409)
    return row, message


def _graph_input(history_id: str, row: dict, message: str) -> dict:
    return {
        "history_id": history_id,
        "mode": row["mode"],
        "weather": row["weather"],
        "notes": row.get("notes") or "",
        "current_item_ids": row["item_ids"],
        "user_message": message,
        "turns": [message],
    }


def _hydrate(history_id: str, row: dict, final: dict) -> dict:
    """Revised outfit in the same hydrated shape as one recommend() entry."""
    full = (
        supabase()
        .table("clothing_items")
        .select("*")
        .in_("id", final["current_item_ids"])
        .execute()
    )
    by_id = {r["id"]: r for r in (full.data or [])}
    return {
        "history_id": history_id,
        "label": "" if row["mode"] == "(default)" else row["mode"],
        "items": [by_id[iid] for iid in final["current_item_ids"] if iid in by_id],
        "reasoning": final.get("reasoning", ""),
        "route": final.get("route", "refine"),
    }


@op  # Weave trace root (#85); the graph's Anthropic calls nest under it.
def refine(history_id: str, message: str) -> dict:
    """One refinement turn against today's outfit row. Returns the revised
    outfit in the same hydrated shape as one recommend() entry, plus the
    route taken."""
    row, message = _load_row(history_id, message)
    final = _APP.invoke(
        _graph_input(history_id, row, message),
        config={"configurable": {"thread_id": history_id}},
    )
    return _hydrate(history_id, row, final)


# #154: node completion -> the stage that starts NEXT. stream_mode="updates"
# reports a node only once it finishes, so labeling the finished node would
# stall the UI on stale text for the whole duration of the slow step; instead
# each tick names what is now running ("context" is emitted up front, before
# the graph moves). refine_outfit/regenerate/persist need no entry: after
# them the `outfit` payload itself is the signal.
STAGE_AFTER_NODE = {
    "load_context": "routing",
    "route": "restyling",
}


def stream(history_id: str, message: str):
    """Yield (event, payload) tuples as the refine graph advances (#154).

    Same node-progress streaming as trip_planner.stream (#124) — the graph
    emits structured JSON, so there's nothing to show token-by-token.
    Validation runs eagerly (RefineError raises here, not in the generator),
    so the SSE route can still return a real 404/409/422.
    """
    row, message = _load_row(history_id, message)

    def generate():
        # Accumulate partial updates over the invoke input; checkpointer-held
        # fields we don't return (pool, prior turns) never surface here.
        final = _graph_input(history_id, row, message)
        yield "progress", {"stage": "context"}
        for update in _APP.stream(
            final.copy(),
            config={"configurable": {"thread_id": history_id}},
            stream_mode="updates",
        ):
            for node_name, partial in update.items():
                # A node's empty-dict return (e.g. load_context on turn 2+)
                # arrives as None rather than {}.
                if partial:
                    final.update(partial)
                stage = STAGE_AFTER_NODE.get(node_name)
                if stage:
                    yield "progress", {"stage": stage}
        yield "outfit", _hydrate(history_id, row, final)
        yield "done", {}

    return generate()
