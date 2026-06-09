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
from datetime import date
from typing import TypedDict

from db.supabase import client as supabase
from langgraph.graph import END, StateGraph
from schemas import (ClothingItem, Gap, PackingCategory, PurchaseResult,
                     PurchaseSuggestion, TripPlanRequest, TripPlanResponse,
                     TripWeather)
from services.claude import client, parse_json
from services.weather import get_weather_for_destination

MODEL = "claude-sonnet-4-6"


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
    purchase_suggestions: list[PurchaseSuggestion]
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

    resp = client().messages.create(
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
    parsed = parse_json(response)

    return {
        "candidate_items": _hydrate_items(parsed["item_ids"], state["catalog"]),
        "gaps": [Gap(**g) for g in parsed.get("gaps", [])],
        "reasoning": parsed["reasoning"],
        "essentials": parsed["essentials"],
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
- Pick the number of items appropriate for the trip duration.
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

Return ONLY a JSON object of the shape:

{
    "item_ids": ["<uuid>", "<uuid>"],
    "gaps": [
        {
            "item": "Linen wide-leg pants",
            "rationale": "for hot daytime walks",
            "category": "bottoms"
        }
    ],
    "essentials": ["Underwear × 5", "Sunscreen"],
    "reasoning": "1-2 sentences explaining the overall pick."
}

No commentary, no markdown fences. The JSON must be parseable.
"""


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
        [item.model_dump(mode="json") for item in state["catalog"]]
    )
    user_blocks.append(catalog_json)

    return user_blocks


def recommend_packing_plan(
    user_blocks: list[str],
):

    resp = client().messages.create(
        model=MODEL,
        max_tokens=2048,
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


def search_purchases_node(state: PackingState) -> dict:

    suggestions = []
    for gap in state["gaps"]:
        suggestions.append(
            PurchaseSuggestion(
                gap=gap,
                results=[
                    PurchaseResult(
                        title=f"{gap.item} (example)",
                        url="https://example.com",
                        image_url="https://placehold.co/300x400",
                        price="$—",
                        retailer="Example",
                    )
                ],
            )
        )
    return {"purchase_suggestions": suggestions}


def build_graph():

    g = StateGraph(PackingState)

    g.add_node("get_weather", get_weather_node)
    g.add_node("infer_weather_if_needed", infer_weather_if_needed_node)
    g.add_node("generate_output", generate_output_node)
    g.add_node("get_catalog", get_catalog_node)
    g.add_node("reason_and_select", reason_and_select_node)
    g.add_node("search_purchases", search_purchases_node)

    g.set_entry_point("get_weather")
    g.add_edge("get_weather", "infer_weather_if_needed")
    g.add_edge("infer_weather_if_needed", "get_catalog")
    g.add_edge("get_catalog", "reason_and_select")

    g.add_conditional_edges(
        "reason_and_select",
        check_gaps,
        {
            "has_gaps": "search_purchases",
            "no_gaps": "generate_output",
        },
    )
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
