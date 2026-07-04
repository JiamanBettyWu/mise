"""Trip planner — agentic packing recommendations.

This module is the integration point for the LangGraph pipeline. It exposes a
single `run(req)` function that the router calls; everything else is internal.

V1 behavior:
- This file ships with `_mock_response()` so the frontend can be built and
  tested without LangGraph in place.
- Replace the body of `run()` with the real LangGraph invocation. The graph
  should return a TripPlanResponse-shaped object.

Useful existing utilities to reuse inside your graph:
- backend.services.weather: today's weather for given coords (needs extension
  for multi-day forecast + destination geocoding).
- backend.services.claude:   Anthropic client + JSON-parse helpers.
- backend.db.supabase:       Supabase client (use service_role; bypass RLS).
"""

import json
import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from db.supabase import client as supabase
from schemas import (
    ClothingItem,
    Gap,
    PackingCategory,
    PackingPlanOutput,
    PurchaseQuery,
    PurchaseResult,
    PurchaseSuggestion,
    ShoppingDepartment,
    TripPlanRequest,
    TripPlanResponse,
    TripWeather,
)
from services.claude import create_tracked, create_tracked_parsed, parse_json
from services.search import search_products
from services.weather import get_weather_for_destination

MODEL = "claude-sonnet-4-6"
# #2: query planning is formatting (≤12-word shopping queries), not
# multi-constraint reasoning — Haiku is plenty, and the deterministic
# fallback in _complete_purchase_queries bounds the downside. The main
# reason_and_select call stays on Sonnet deliberately.
QUERY_PLANNING_MODEL = "claude-haiku-4-5-20251001"
log = logging.getLogger("wardrobe.trip_planner")

DEFAULT_SHOPPING_DEPARTMENT: ShoppingDepartment = "womens"
SHOPPING_DEPARTMENTS = {"womens", "mens", "unisex", "no_preference"}
DEPARTMENT_QUERY_TERMS = {
    "womens": "women's",
    "mens": "men's",
    "unisex": "unisex",
    "no_preference": "",
}
DEPARTMENTED_CATEGORIES = {"tops", "bottoms", "dresses", "outerwear", "shoes"}


class PackingState(TypedDict, total=False):
    # seeded from request
    destination: str
    start_date: date
    end_date: date
    additional_notes: str
    lat: float | None
    lon: float | None

    # filled in by nodes
    weather: TripWeather
    catalog: list[ClothingItem]
    candidate_items: list[ClothingItem]
    packing_list: list[PackingCategory]
    essentials: list[str]
    gaps: list[Gap]
    purchase_queries: list[PurchaseQuery]
    purchase_suggestions: list[PurchaseSuggestion]
    shopping_department: ShoppingDepartment
    user_preferences: list[str]
    inferred_preferences: list[str]
    reasoning: str


def get_weather_node(state: PackingState) -> dict:
    weather = get_weather_for_destination(
        destination=state["destination"],
        start_date=state["start_date"],
        end_date=state["end_date"],
        lat=state.get("lat"),
        lon=state.get("lon"),
    )

    return {"weather": weather}


CLIMATE_INFERENCE_SYSTEM_PROMPT = """You estimate destination climate for travel packing.

Given a destination, travel dates, and any available forecast context, return a concise
trip-level climate estimate for dates not covered by a live forecast.

Rules:
- Do not invent exact daily temperatures.
- Do not present this as a live weather forecast.
- Mention uncertainty briefly.
- Focus on packing-relevant conditions: heat/cold, humidity, rain, wind, sun, and layers.

Return ONLY a JSON object of the shape:

{
  "inferred_summary": "1-2 sentences"
}

No commentary, no markdown fences. The JSON must be parseable.
"""


def infer_weather_if_needed_node(state: PackingState) -> dict:
    weather = state["weather"]
    if weather.coverage == "full_forecast":
        return {}

    inferred_summary = infer_climate_summary(state)
    if weather.forecast_summary:
        summary = f"{weather.forecast_summary} {inferred_summary}"
    else:
        summary = inferred_summary

    return {
        "weather": weather.model_copy(
            update={
                "summary": summary,
                "inferred_summary": inferred_summary,
            }
        )
    }


def infer_climate_summary(state: PackingState) -> str:
    weather = state["weather"]
    duration = (state["end_date"] - state["start_date"]).days + 1
    user_blocks = [
        f"Destination: {state['destination']}",
        f"Dates: {state['start_date']} to {state['end_date']} ({duration} days)",
        f"Weather coverage: {weather.coverage}",
        f"Available forecast summary: {weather.forecast_summary or 'None'}",
        "Infer climate only for trip dates not covered by the available forecast.",
    ]
    additional_notes = state.get("additional_notes", "")
    if additional_notes.strip():
        user_blocks.append(f"User notes: {additional_notes.strip()}")

    resp = create_tracked(
        "trip_climate_infer",
        model=MODEL,
        max_tokens=256,
        system=[
            {
                "type": "text",
                "text": CLIMATE_INFERENCE_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "\n\n".join(user_blocks)}],
    )
    parsed = parse_json(resp)
    return parsed.get(
        "inferred_summary",
        "Climate estimate unavailable; pack conservatively for the destination and season.",
    )


def get_catalog_node(state: PackingState):
    rows = (
        supabase()
        .table("clothing_items")
        .select("*")
        .eq("available", True)
        .execute()
        .data
        or []
    )
    return {"catalog": [ClothingItem(**row) for row in rows]}


def reason_and_select_node(state: PackingState):
    user_prompt = _build_packing_prompt(state)  # helper that formats the inputs

    response = recommend_packing_plan(user_prompt)
    parsed: PackingPlanOutput = response.content[0].parsed_output

    return {
        "candidate_items": _hydrate_items(parsed.item_ids, state["catalog"]),
        "gaps": parsed.gaps,
        "reasoning": parsed.reasoning,
        "essentials": parsed.essentials,
    }


def generate_output_node(state: PackingState) -> dict:
    items_by_category = {}

    for item in state.get("candidate_items", []):
        cat = _categorize(item.type)
        items_by_category.setdefault(cat, []).append(item)

    packing_list = [
        PackingCategory(category=cat, items=items)
        for cat, items in items_by_category.items()
    ]

    return {"packing_list": packing_list}


PACKING_SYSTEM_PROMPT = """You are a travel advisor. Given the travel destination, trip duration, 
weather forecasts and a wardrobe inventory, recommend a packing plan for the trip. 

The packing plan should:
- Include all categories of clothing items a person would wear: top + bottom (or dress) + shoes, 
  plus outerwears if needed.
- Be weather-appropriate (layers for cold, breathable for heat, water-resistant if rain is forecasted).
- If weather context includes a climate estimate, use it conservatively and do not treat it as a live forecast.
- Scale quantities with trip duration: include at least 3 top-slot items (tops or dresses,
  combined) — or one per day if the trip is shorter than 3 days. More than 3 is fine for
  longer trips, but not required: re-wearing on long trips is normal packing advice.
- Reference each item by its `id`, unless for `gaps` and `essentials`. 


`gaps` is a list of `{item, rationale, category}` objects. item is the specific missing thing (3–6 words, no articles).
rationale is one sentence explaining why this trip needs it. category is one of: tops, bottoms, dresses, outerwear, 
shoes, accessories. Gaps identified should be appropriate for specific weather conditions and destination.
If there is no gap identified, you can return the entry with `gaps:[]`.

In addition to picking outfits from the provided inventory, you should also add other reasonable packing 
essentials beyond the inventory. The essentials should also tailor to the travel destination, weather, 
and trip length. Examples are underwear, socks, scarf, gloves, hats, sunscreen, passport, charger, ...
Don't repeat anything already in the selected items. Be specific where it matters (e.g. 'rain jackets' not 
just 'outerwear') and skip the obvious (don't just say 'clothes'). Tailor it to the destination (e.g. adapter 
for international trips, sunscreen for sunny climates). Aim for 5 ~ 10 items in total.
"""


# #2: only the fields the model needs for styling decisions ride the prompt —
# `warmth` stays in (the prompt reasons over weather; it's the cold/heat
# signal from #40). Dropped: photo_url, available, in_travel_bag, notes,
# created_at.
PACKING_PROMPT_ITEM_FIELDS = {
    "id",
    "name",
    "type",
    "color",
    "formality",
    "season",
    "fabric",
    "warmth",
    "description",
    "brand",
}


def _build_packing_prompt(
    state,
):
    duration = (state["end_date"] - state["start_date"]).days + 1

    user_blocks = [
        f"Destination: {state['destination']}",
        f"Dates: {state['start_date']} to {state['end_date']} ({duration} days)",
        f"Weather: {state['weather'].summary}",
    ]
    additional_notes = state["additional_notes"]
    if additional_notes.strip():
        user_blocks.append(f"User notes for today: {additional_notes.strip()}")
    user_blocks.append("Wardrobe inventory (JSON):")

    catalog_json = json.dumps(
        [
            {
                k: v
                for k, v in item.model_dump(mode="json").items()
                if k in PACKING_PROMPT_ITEM_FIELDS
            }
            for item in state["catalog"]
        ]
    )
    user_blocks.append(catalog_json)

    return user_blocks


def recommend_packing_plan(
    user_blocks: list[str],
):

    resp = create_tracked_parsed(
        "trip_plan",
        PackingPlanOutput,
        model=MODEL,
        max_tokens=2048,
        # #120: structured selection (pick ids, emit JSON) doesn't need the
        # default temperature 1.0; low temp narrows run-to-run spread. The
        # explicit quantity rule in the prompt moves the center — temp alone
        # would just make a borderline judgment consistently borderline.
        temperature=0.2,
        system=[
            {
                "type": "text",
                "text": PACKING_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "\n\n".join(user_blocks)}],
    )

    return resp


def check_gaps(state: PackingState) -> str:
    return "has_gaps" if state.get("gaps") else "no_gaps"


PURCHASE_QUERY_SYSTEM_PROMPT = """You plan concise Google Shopping queries for missing travel wardrobe items.

Given a trip context, shopping department, missing packing gaps, and optional preferences,
write one search query per gap.

Rules:
- Include shopping department for apparel and footwear by default.
- Omit shopping department for naturally unisex items when it is not useful.
- If shopping_department is no_preference, omit department terms.
- Use user-authored preferences only when directly relevant to the item being purchased.
- Use learned preferences only as soft style hints.
- User-authored preferences outrank learned preferences on conflict.
- It is valid to use no preferences.
- Do not force outfit-composition preferences into the query unless they clearly affect this item.
- Prefer concrete shopping terms over abstract aesthetic language.
- Keep each query under 12 words.

Return ONLY a JSON object of the shape:

{
  "queries": [
    {
      "gap_index": 0,
      "query": "women's lightweight neutral rain jacket city travel",
      "rationale": "Used the department and rain/city context; no outfit-composition prefs applied.",
      "used_preferences": ["Prefers neutral basics"]
    }
  ]
}

No commentary, no markdown fences. The JSON must be parseable.
"""


def plan_purchase_queries_node(state: PackingState) -> dict:
    gaps = state.get("gaps", [])
    if not gaps:
        return {"purchase_queries": []}

    shopping_department, user_preferences, inferred_preferences = (
        _get_purchase_context()
    )

    try:
        planned = plan_purchase_queries(
            state,
            shopping_department=shopping_department,
            user_preferences=user_preferences,
            inferred_preferences=inferred_preferences,
        )
    except Exception:
        log.warning(
            "purchase query planning failed; using fallback queries", exc_info=True
        )
        planned = []

    return {
        "shopping_department": shopping_department,
        "user_preferences": user_preferences,
        "inferred_preferences": inferred_preferences,
        "purchase_queries": _complete_purchase_queries(
            planned,
            gaps,
            shopping_department,
        ),
    }


def plan_purchase_queries(
    state: PackingState,
    shopping_department: ShoppingDepartment,
    user_preferences: list[str],
    inferred_preferences: list[str],
) -> list[PurchaseQuery]:
    user_blocks = _build_purchase_query_prompt(
        state,
        shopping_department=shopping_department,
        user_preferences=user_preferences,
        inferred_preferences=inferred_preferences,
    )

    resp = create_tracked(
        "purchase_query_plan",
        model=QUERY_PLANNING_MODEL,
        max_tokens=768,
        system=[
            {
                "type": "text",
                "text": PURCHASE_QUERY_SYSTEM_PROMPT,
                "cache_control": {"type": "ephemeral"},
            }
        ],
        messages=[{"role": "user", "content": "\n\n".join(user_blocks)}],
    )
    parsed = parse_json(resp)

    queries = []
    for raw in parsed.get("queries", []):
        if not isinstance(raw, dict):
            continue
        query = _clean_purchase_query(str(raw.get("query", "")))
        if not query:
            continue
        try:
            queries.append(PurchaseQuery(**{**raw, "query": query}))
        except Exception:
            log.info("dropping malformed purchase query: %r", raw)
    return queries


def _get_purchase_context() -> tuple[ShoppingDepartment, list[str], list[str]]:
    shopping_department = DEFAULT_SHOPPING_DEPARTMENT
    try:
        res = supabase().table("profile").select("*").limit(1).execute()
        if res.data:
            shopping_department = _normalize_shopping_department(
                res.data[0].get("shopping_department")
            )
    except Exception:
        log.warning("could not read profile shopping_department", exc_info=True)

    try:
        res = (
            supabase()
            .table("preferences")
            .select("text, source")
            .eq("status", "active")
            .order("created_at")
            .execute()
        )
        user, inferred = [], []
        for row in res.data or []:
            (inferred if row.get("source") == "inferred" else user).append(row["text"])
        return shopping_department, user, inferred
    except Exception:
        log.warning("could not read preferences for purchase planning", exc_info=True)
        return shopping_department, [], []


def _build_purchase_query_prompt(
    state: PackingState,
    shopping_department: ShoppingDepartment,
    user_preferences: list[str],
    inferred_preferences: list[str],
) -> list[str]:
    duration = (state["end_date"] - state["start_date"]).days + 1
    gaps_json = json.dumps(
        [
            {
                "gap_index": i,
                "item": gap.item,
                "category": gap.category,
                "rationale": gap.rationale,
            }
            for i, gap in enumerate(state.get("gaps", []))
        ],
    )

    user_blocks = [
        f"Destination: {state['destination']}",
        f"Dates: {state['start_date']} to {state['end_date']} ({duration} days)",
        f"Weather: {state['weather'].summary}",
        f"shopping_department: {shopping_department}",
        "Missing gaps (JSON):",
        gaps_json,
    ]

    additional_notes = state.get("additional_notes", "")
    if additional_notes.strip():
        user_blocks.append(f"User trip notes: {additional_notes.strip()}")

    if user_preferences:
        user_blocks.append(
            "User-authored preferences (hard constraints only when applicable):\n"
            + "\n".join(f"- {p}" for p in user_preferences)
        )
    if inferred_preferences:
        user_blocks.append(
            "Learned preferences (soft hints; ignore when irrelevant):\n"
            + "\n".join(f"- {p}" for p in inferred_preferences)
        )

    return user_blocks


def _complete_purchase_queries(
    planned: list[PurchaseQuery],
    gaps: list[Gap],
    shopping_department: ShoppingDepartment,
) -> list[PurchaseQuery]:
    by_index = {}
    for purchase_query in planned:
        if (
            purchase_query.gap_index >= len(gaps)
            or purchase_query.gap_index in by_index
        ):
            continue
        query = _clean_purchase_query(purchase_query.query)
        if query:
            by_index[purchase_query.gap_index] = purchase_query.model_copy(
                update={"query": query}
            )

    return [
        by_index.get(
            i,
            PurchaseQuery(
                gap_index=i,
                query=fallback_purchase_query(gap, shopping_department),
                rationale="Fallback query used because the planner did not return a usable query.",
            ),
        )
        for i, gap in enumerate(gaps)
    ]


def fallback_purchase_query(
    gap: Gap,
    shopping_department: ShoppingDepartment | str = DEFAULT_SHOPPING_DEPARTMENT,
) -> str:
    department = _normalize_shopping_department(shopping_department)
    department_term = DEPARTMENT_QUERY_TERMS[department]
    if not department_term or gap.category not in DEPARTMENTED_CATEGORIES:
        return _clean_purchase_query(gap.item)
    return _clean_purchase_query(f"{department_term} {gap.item}")


def _normalize_shopping_department(value: object) -> ShoppingDepartment:
    if value in SHOPPING_DEPARTMENTS:
        return value  # type: ignore[return-value]
    return DEFAULT_SHOPPING_DEPARTMENT


def _clean_purchase_query(query: str) -> str:
    return " ".join(query.strip().split()[:12])


def search_purchases_node(state: PackingState) -> dict:
    queries_by_index = {q.gap_index: q for q in state.get("purchase_queries", [])}
    shopping_department = state.get("shopping_department", DEFAULT_SHOPPING_DEPARTMENT)

    gaps = state["gaps"]
    if not gaps:
        return {"purchase_suggestions": []}

    queries = []
    for i, gap in enumerate(gaps):
        fallback = PurchaseQuery(
            gap_index=i,
            query=fallback_purchase_query(gap, shopping_department),
        )
        queries.append(queries_by_index.get(i, fallback).query)

    def _search_one(query: str) -> list[PurchaseResult]:
        # Best-effort per gap: any failure keeps the gap visible with
        # results=[] instead of sinking the sibling searches.
        try:
            return search_products(query, 4)
        except Exception:
            log.warning("purchase search failed for %r", query, exc_info=True)
            return []

    # #107: the queries are independent and purely network-bound, so run them
    # concurrently — the node costs the slowest search, not the sum.
    with ThreadPoolExecutor(max_workers=min(8, len(gaps))) as pool:
        results = list(pool.map(_search_one, queries))

    return {
        "purchase_suggestions": [
            PurchaseSuggestion(gap=gap, results=res) for gap, res in zip(gaps, results)
        ]
    }


def build_graph():

    g = StateGraph(PackingState)

    g.add_node("get_weather", get_weather_node)
    g.add_node("infer_weather_if_needed", infer_weather_if_needed_node)
    g.add_node("generate_output", generate_output_node)
    g.add_node("get_catalog", get_catalog_node)
    g.add_node("reason_and_select", reason_and_select_node)
    g.add_node("plan_purchase_queries", plan_purchase_queries_node)
    g.add_node("search_purchases", search_purchases_node)

    # #2: weather and catalog are independent — fan out from START so the
    # catalog fetch doesn't wait behind the weather branch (which includes a
    # 1-3s Claude climate-inference call for most real trips).
    g.add_edge(START, "get_weather")
    g.add_edge(START, "get_catalog")
    g.add_edge("get_weather", "infer_weather_if_needed")
    # The branches are different lengths, so join with the list form: it defers
    # reason_and_select until BOTH parents have run. Two separate add_edge
    # calls would trigger it as soon as the shorter catalog branch finished.
    g.add_edge(["infer_weather_if_needed", "get_catalog"], "reason_and_select")

    g.add_conditional_edges(
        "reason_and_select",
        check_gaps,
        {
            "has_gaps": "plan_purchase_queries",
            "no_gaps": "generate_output",
        },
    )
    g.add_edge("plan_purchase_queries", "search_purchases")
    g.add_edge("search_purchases", "generate_output")

    g.add_edge("generate_output", END)

    return g.compile()


# ---- Public entrypoint ----------------------------------------------------

_APP = build_graph()


def run(req: TripPlanRequest) -> TripPlanResponse:
    """Generate a packing plan for the trip."""

    initial_state: PackingState = {
        "destination": req.destination,
        "start_date": req.start_date,
        "end_date": req.end_date,
        "additional_notes": req.additional_notes,
        "lat": req.lat,
        "lon": req.lon,
    }

    final_state = _APP.invoke(initial_state)

    return TripPlanResponse(
        destination=req.destination,
        start_date=req.start_date,
        end_date=req.end_date,
        duration_days=(req.end_date - req.start_date).days + 1,
        weather=final_state["weather"],
        packing_list=final_state.get("packing_list", []),
        gaps=final_state.get("gaps", []),
        purchase_suggestions=final_state.get("purchase_suggestions", []),
        reasoning=final_state.get("reasoning", ""),
        essentials=final_state.get("essentials", []),
    )


def _categorize(item_type: str) -> str:
    t = (item_type or "").lower()
    if t == "dress":
        return "dresses"
    if t in {"shirt", "t-shirt", "blouse", "sweater"}:
        return "tops"
    if t in {"trousers", "jeans", "shorts", "skirt"}:
        return "bottoms"
    if t in {"jacket", "coat", "vest"}:
        return "outerwear"
    if t in {"shoes", "boots", "sneakers", "sandals"}:
        return "shoes"
    if t in {"bag", "scarf", "hat", "belt", "accessory"}:
        return "accessories"
    return "other"


def _hydrate_items(
    item_ids: list[str], catalog: list[ClothingItem]
) -> list[ClothingItem]:
    by_id = {item.id: item for item in catalog}
    return [by_id[iid] for iid in item_ids if iid in by_id]
