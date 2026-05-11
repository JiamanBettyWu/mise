# Trip Planning Feature Plan
### AI Outfit Recommender — Packing Planner Module

---

## Overview

Transform the outfit recommender from a daily recommendation tool into a full trip planning assistant using a LangGraph agentic pipeline. The packing planner takes trip details as input and generates intelligent, weather-aware, activity-appropriate packing recommendations with day-by-day outfit combinations.

---

## Problem Statement

Current system limitations for trip planning:
- Daily recommendations don't account for multi-day trip context
- No awareness of destination weather over trip duration
- No cross-day outfit coordination (avoiding repetition, maximizing versatility)
- No gap detection for missing items
- No purchase recommendations for wardrobe gaps

---

## Architecture Overview

### Why LangGraph?

The current outfit system is a **pipeline** — fixed sequential steps. The packing planner needs to be **agentic** — it must make decisions based on what it finds:

- Does Betty have enough items for the trip? → Maybe search for purchases
- What's the weather like? → Adjust recommendations accordingly  
- Does the calendar have structured itinerary? → Generate day-by-day vs simple list

LangGraph models this as a **graph** with nodes (actions) and conditional edges (decisions).

### State Object

```python
from typing import TypedDict, List, Optional

class PackingState(TypedDict):
    # Trip inputs
    destination: str
    start_date: str
    end_date: str
    duration_days: int
    additional_notes: str          # "mole making class day 4, cobblestone streets"
    itinerary: Optional[List[dict]] # manual day-by-day OR from calendar
    
    # Retrieved data
    weather: Optional[dict]         # fetched from weather API
    catalog_items: Optional[List[dict]]  # from database
    
    # Preferences
    user_preferences: dict          # explicit + inferred from catalog
    
    # Reasoning outputs
    candidate_items: Optional[List[dict]]
    identified_gaps: Optional[List[str]]
    purchase_suggestions: Optional[List[dict]]
    
    # Final output
    packing_list: Optional[List[dict]]
    day_by_day_outfits: Optional[List[dict]]  # if itinerary available
    reasoning: Optional[str]
```

### Graph Structure

```
[START]
    ↓
[get_weather]
Weather API call for destination + dates
    ↓
[get_catalog]
Fetch catalog from database
Filter travel-relevant items
    ↓
[infer_preferences]
Analyze catalog to infer aesthetic preferences
Combine with explicit user preferences
    ↓
[get_itinerary]
Check if manual itinerary provided OR calendar connected
    ↓
[reason_and_select]
Claude reasons over weather + catalog + activities + preferences
Selects candidate items
Identifies gaps
    ↓
[check_gaps] ← conditional edge
    ↓                    ↓
[gaps exist]         [no gaps]
    ↓                    ↓
[search_purchases]  [generate_output]
Searches online          ↓
for missing items    [generate_output]
    ↓
[generate_output]
Day-by-day outfits (if itinerary available)
OR simple packing list (if no itinerary)
    ↓
[END]
```

---

## Node Implementations

### Node 1: get_weather
```python
def get_weather(state: PackingState) -> PackingState:
    """
    Fetch weather forecast for destination across trip dates.
    Returns: temperature range, conditions, precipitation probability
    """
    weather_data = weather_api.forecast(
        destination=state["destination"],
        start_date=state["start_date"],
        end_date=state["end_date"]
    )
    return {**state, "weather": weather_data}
```

### Node 2: get_catalog
```python
def get_catalog(state: PackingState) -> PackingState:
    """
    Fetch clothing catalog from database.
    Filters for travel-relevant categories.
    Respects travel_mode status (excludes already packed items).
    """
    catalog = db.get_catalog(
        exclude_laundry=True,
        categories=["tops", "bottoms", "dresses", "outerwear", 
                   "shoes", "accessories"]
    )
    return {**state, "catalog_items": catalog}
```

### Node 3: infer_preferences
```python
def infer_preferences(state: PackingState) -> PackingState:
    """
    Two-layer preference system:
    1. Explicit: manually set by user in profile
    2. Inferred: analyzed from catalog patterns
    
    Preference hierarchy:
    - Explicit constraints (highest) e.g. "no satin in cold weather"
    - Explicit preferences e.g. "pastels and neutrals"
    - Inferred preferences e.g. "catalog shows preference for relaxed fits"
    - General styling rules (lowest)
    """
    explicit_prefs = db.get_user_preferences()
    
    inferred_prefs = claude_api.infer_from_catalog(
        catalog=state["catalog_items"],
        prompt="Analyze this catalog and infer color, style, and fit preferences"
    )
    
    combined_preferences = {
        "explicit": explicit_prefs,
        "inferred": inferred_prefs,
    }
    
    return {**state, "user_preferences": combined_preferences}
```

> **Note:** Catalog inference becomes more accurate as catalog grows. Meaningful results expected at 60-70+ items. Currently best to rely on explicit preferences until catalog is sufficiently large.

### Node 4: get_itinerary
```python
def get_itinerary(state: PackingState) -> PackingState:
    """
    Three modes (in priority order):
    1. Calendar mode (if enabled): fetch from Google Calendar API
    2. Manual mode: parse day-by-day from additional_notes
    3. Simple mode: no structured itinerary, use notes only
    """
    if state.get("calendar_enabled"):
        itinerary = google_calendar.get_events(
            start=state["start_date"],
            end=state["end_date"]
        )
    elif has_day_structure(state["additional_notes"]):
        itinerary = parse_manual_itinerary(state["additional_notes"])
    else:
        itinerary = None  # simple packing list mode
        
    return {**state, "itinerary": itinerary}
```

### Node 5: reason_and_select
```python
def reason_and_select(state: PackingState) -> PackingState:
    """
    Core Claude reasoning node.
    Selects optimal items from catalog.
    Identifies wardrobe gaps.
    """
    prompt = f"""
    Trip: {state['destination']} for {state['duration_days']} days
    Weather: {state['weather']}
    Activities: {state['additional_notes']}
    Itinerary: {state['itinerary']}
    Available items: {state['catalog_items']}
    User preferences: {state['user_preferences']}
    
    Select optimal packing items considering:
    - Weather appropriateness
    - Activity suitability  
    - Outfit versatility and mix-and-match potential
    - User aesthetic preferences
    - Minimizing total items while maximizing outfit combinations
    
    Identify any critical gaps not covered by current catalog.
    
    Return JSON: selected_items, gaps, reasoning
    """
    response = claude_api.call(prompt)
    return {**state, 
            "candidate_items": response.selected_items,
            "identified_gaps": response.gaps,
            "reasoning": response.reasoning}
```

### Node 6: check_gaps (Conditional Edge)
```python
def check_gaps(state: PackingState) -> str:
    """
    Conditional edge — determines next node.
    """
    if state["identified_gaps"]:
        return "search_purchases"
    return "generate_output"
```

### Node 7: search_purchases
```python
def search_purchases(state: PackingState) -> PackingState:
    """
    For each identified gap, search for purchase options.
    Filters results by user aesthetic preferences.
    """
    suggestions = []
    for gap in state["identified_gaps"]:
        results = web_search.search(
            query=f"{gap} {state['user_preferences']['explicit']['style']}",
            filters=state["user_preferences"]
        )
        suggestions.append(results)
    
    return {**state, "purchase_suggestions": suggestions}
```

### Node 8: generate_output
```python
def generate_output(state: PackingState) -> PackingState:
    """
    Two output modes based on itinerary availability:
    
    Mode A (no itinerary): Simple categorized packing list
    Mode B (itinerary available): Day-by-day outfit combinations
    """
    if state["itinerary"]:
        # Day-by-day outfit combinations
        output = generate_day_by_day(state)
    else:
        # Simple packing list by category
        output = generate_packing_list(state)
        
    return {**state, 
            "packing_list": output.items,
            "day_by_day_outfits": output.daily_outfits}
```

---

## LangGraph Assembly

```python
from langgraph.graph import StateGraph, END

graph = StateGraph(PackingState)

# Add all nodes
graph.add_node("get_weather", get_weather)
graph.add_node("get_catalog", get_catalog)
graph.add_node("infer_preferences", infer_preferences)
graph.add_node("get_itinerary", get_itinerary)
graph.add_node("reason_and_select", reason_and_select)
graph.add_node("search_purchases", search_purchases)
graph.add_node("generate_output", generate_output)

# Linear edges
graph.set_entry_point("get_weather")
graph.add_edge("get_weather", "get_catalog")
graph.add_edge("get_catalog", "infer_preferences")
graph.add_edge("infer_preferences", "get_itinerary")
graph.add_edge("get_itinerary", "reason_and_select")

# Conditional edge — the agentic decision
graph.add_conditional_edges(
    "reason_and_select",
    check_gaps,
    {
        "search_purchases": "search_purchases",
        "generate_output": "generate_output"
    }
)

graph.add_edge("search_purchases", "generate_output")
graph.add_edge("generate_output", END)

app = graph.compile()
```

---

## UI Design

### New Tab: Trip Planning

```
┌─────────────────────────────────────────┐
│  📍 Destination                          │
│  [Oaxaca, Mexico                       ] │
│                                          │
│  📅 Travel Dates                         │
│  From: [May 17, 2026] To: [May 21, 2026] │
│                                          │
│  🌤️ Weather (auto-fetched)               │
│  28°C, Sunny, Low humidity               │
│                                          │
│  📝 Activities & Notes                   │
│  [City exploring, Monte Albán ruins,   ] │
│  [mole making class on last day,       ] │
│  [evening dining, cobblestone streets  ] │
│                                          │
│  📅 Calendar Integration    [OFF ●○○]    │
│  (Connect Google Calendar for           │
│   day-by-day recommendations)           │
│                                          │
│  ┌──────────────────────────────────┐   │
│  │   Generate Packing Plan 🧳        │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘

── Generated Plan ─────────────────────────

Simple Mode (no calendar):

👗 Dresses
  • Lilac maxi dress ✓

👖 Bottoms  
  • Linen wide-leg pants ⚠️ Purchase recommended

👟 Shoes
  • White tennis shoes ✓
  • Sporty sandals ✓
  • Flats ✓

🛍️ Purchase Recommendations
  • Linen wide-leg pants — [Search Results]

─────────────────────────────────────────
Calendar Mode (when enabled):

Day 1 — Arrival + City Exploring
  Top: White ribbed boat-neck top
  Bottom: Linen wide-leg pants
  Shoes: White tennis shoes

Day 2 — Monte Albán Ruins
  ...

─────────────────────────────────────────
[Edit Plan ✏️]    [Share via Email 📧]
```

---

## Output Modes

### Mode A: Simple Packing List
*Triggered when: no calendar, no structured itinerary in notes*

Output:
- Items grouped by category
- Purchase recommendations for gaps
- Total item count
- Versatility notes

### Mode B: Day-by-Day Outfits
*Triggered when: calendar connected OR manual day structure in notes*

Output:
- Complete outfit per day
- Accounts for activity + weather per day
- Shows item reuse across days
- Avoids outfit repetition
- Purchase recommendations if gaps exist

---

## User Aesthetic Preferences

Incorporated at the `reason_and_select` and `search_purchases` nodes.

### Two-Layer System

**Layer 1: Explicit Preferences** (user defined)
```json
{
  "colors": ["pastels", "neutrals", "muted tones"],
  "avoid": ["neon", "loud prints", "excessive satin"],
  "style": ["smart casual", "elevated", "athleisure"],
  "fit": ["relaxed", "tailored"],
  "temperature_sensitivity": "runs cold"
}
```

**Layer 2: Inferred Preferences** (catalog analyzed)
- Auto-generated by analyzing existing catalog
- Updates automatically as catalog grows
- Meaningful at 60-70+ catalog items
- Catches nuances not captured in explicit preferences

### Preference Hierarchy
```
Explicit constraints     ← highest priority
Explicit preferences
Inferred preferences
General styling rules    ← lowest priority
```

---

## V1 Build Plan (Pre-Oaxaca)

**Goal:** Basic working pipeline for Oaxaca stress test

### Scope
- ✅ Trip input form (destination, dates, notes)
- ✅ Weather auto-fetch on destination input
- ✅ Catalog retrieval
- ✅ Basic LangGraph graph (no calendar)
- ✅ Simple packing list output
- ✅ Gap detection + purchase suggestions
- ✅ User editing of generated plan
- ✅ Share via email
- ❌ Calendar integration (V2)
- ❌ Day-by-day outfits without calendar (V2)
- ❌ Catalog inference of preferences (V2, needs 60-70+ items)

### Tonight's Minimal Goal
Get basic graph skeleton running end to end:
```
get_weather → get_catalog → reason_and_select → generate_output
```
No conditional edges yet. Just prove the graph runs.

### Oaxaca Stress Test Criteria
- ✅ Pass: recommends lilac maxi dress 💜
- ✅ Pass: suggests comfortable walking shoes for cobblestones
- ✅ Pass: flags linen pants as purchase recommendation
- ✅ Pass: weather appropriate recommendations for 28°C
- ❌ Fail: recommends satin tube top for ruins tour
- ❌ Fail: calls lilac maxi dress "grey midi" again

---

## V2 Build Plan (Post-Oaxaca)

### Google Calendar Integration

**Prerequisites:**
- Apple Calendar → Google Calendar sync already configured ✅
- Trip events manually added to Google account in Apple Calendar ✅

**Implementation steps:**

1. **Google Cloud Console setup**
   - Create project
   - Enable Google Calendar API
   - Create OAuth 2.0 credentials
   - Configure consent screen
   - Set redirect URIs

2. **OAuth flow implementation**
```python
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build

def get_calendar_events(start_date: str, end_date: str):
    flow = Flow.from_client_config(
        client_config=GOOGLE_CLIENT_CONFIG,
        scopes=["https://www.googleapis.com/auth/calendar.readonly"]
    )
    # Handle token storage and refresh
    service = build("calendar", "v3", credentials=creds)
    events = service.events().list(
        calendarId="primary",
        timeMin=start_date,
        timeMax=end_date,
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    return events.get("items", [])
```

3. **Event parsing for outfit context**
```python
def parse_event_for_outfit_context(event: dict) -> dict:
    """
    Map calendar event titles to outfit requirements.
    Examples:
    "Board meeting" → formal
    "Lunch with Sarah" → smart casual  
    "Solidcore" → athleisure
    "Mole making class" → smart casual, splash-resistant
    "Monte Albán ruins" → casual, comfortable, sun protection
    """
    return claude_api.classify_event(
        event_title=event["summary"],
        event_description=event.get("description", ""),
        prompt="Classify this event's outfit requirements"
    )
```

4. **UI calendar toggle**
```
[📅 Use Calendar for Day-by-Day Recommendations  ●○○ OFF]
↓ when toggled ON:
[Connect Google Calendar] → OAuth flow → events loaded
```

**Data flow with calendar:**
```
Apple Calendar (Betty adds events)
        ↓ auto-sync
Google Calendar
        ↓ API call
LangGraph get_itinerary node
        ↓ parse events
Day-by-day outfit recommendations
```

### Additional V2 Features
- Catalog preference inference (at 60-70+ items)
- Multi-destination trip support
- Packing list export (PDF)
- Post-trip feedback: "did you wear this?" → improves future recommendations
- Model optimization: use Haiku for simple nodes, Sonnet for reasoning nodes


*Last updated: May 2026*
*Status: V1 in development*
*Oaxaca stress test: May 17-21, 2026* 🌮