from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Formality = Literal["casual", "smart-casual", "formal"]
Season = Literal["spring", "summer", "fall", "winter", "all-season"]
ShoppingDepartment = Literal["womens", "mens", "unisex", "no_preference"]

TripCategory = Literal[
    "tops",
    "bottoms",
    "dresses",
    "outerwear",
    "shoes",
    "accessories",
    "other",
]


class ClothingItemBase(BaseModel):
    name: str = Field(..., max_length=80)
    type: str
    color: str
    formality: Formality
    season: Season
    fabric: str
    # 1 = minimal warmth … 5 = maximum; None = not rated (e.g. bags, belts).
    # Inferred at tagging, hand-editable in the UI; inference fills nulls only.
    warmth: Optional[int] = Field(default=None, ge=1, le=5)
    description: str = ""
    brand: Optional[str] = None
    notes: Optional[str] = None


class ClothingItemCreate(ClothingItemBase):
    photo_url: str
    available: bool = True
    in_travel_bag: bool = False


class ClothingItemUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=80)
    type: Optional[str] = None
    color: Optional[str] = None
    formality: Optional[Formality] = None
    season: Optional[Season] = None
    fabric: Optional[str] = None
    warmth: Optional[int] = Field(default=None, ge=1, le=5)
    description: Optional[str] = None
    brand: Optional[str] = None
    notes: Optional[str] = None
    available: Optional[bool] = None
    in_travel_bag: Optional[bool] = None


class ClothingItem(ClothingItemCreate):
    id: str
    created_at: datetime


class TagSuggestion(ClothingItemBase):
    """What Claude returns from a vision tagging call."""

    photo_url: str = Field(..., description="Public URL of the uploaded photo")


# ---- Profile & preferences ------------------------------------------------


class PreferenceCreate(BaseModel):
    text: str = Field(..., min_length=1, max_length=500)


class PreferenceUpdate(BaseModel):
    text: Optional[str] = Field(default=None, min_length=1, max_length=500)
    status: Optional[Literal["active", "rejected"]] = None


class Preference(BaseModel):
    id: str
    text: str
    source: Literal["user", "inferred"]
    status: Literal["active", "rejected"]
    evidence_ids: list[str] = []
    created_at: datetime
    updated_at: datetime


class ProfileUpdate(BaseModel):
    home_location_text: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    shopping_department: Optional[ShoppingDepartment] = None


class Profile(BaseModel):
    id: Optional[str] = None
    home_location_text: Optional[str] = None
    home_lat: Optional[float] = None
    home_lon: Optional[float] = None
    shopping_department: ShoppingDepartment = "womens"
    updated_at: Optional[datetime] = None
    # Heartbeat for the weekly inference job (#62): last successful run, surfaced
    # in the profile UI as relative time. Read-only — not in ProfileUpdate, so
    # the PUT /profile form can't clobber it.
    preferences_reviewed_at: Optional[datetime] = None


# ---- Trip planner ---------------------------------------------------------


class TripPlanRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=200)
    start_date: date
    end_date: date
    additional_notes: str = ""
    # Optional pre-geocoded coords from the destination autocomplete. When
    # present, the weather node skips its own OWM /geo lookup.
    lat: float | None = None
    lon: float | None = None


class TripWeatherDay(BaseModel):
    date: date
    high_c: float
    low_c: float
    conditions: str
    precip_chance: float = Field(..., ge=0, le=1)


class TripWeather(BaseModel):
    summary: str
    daily: list[TripWeatherDay] = []
    coverage: Literal["full_forecast", "partial_forecast", "inferred_climate"]
    forecast_summary: Optional[str] = None
    inferred_summary: Optional[str] = None


class PackingCategory(BaseModel):
    category: TripCategory
    items: list[ClothingItem]


class PurchaseResult(BaseModel):
    title: str
    url: str
    image_url: Optional[str] = None
    price: Optional[str] = None
    retailer: Optional[str] = None


class Gap(BaseModel):
    item: str
    rationale: str
    category: TripCategory


class PackingPlanOutput(BaseModel):
    """Structured-output schema for the trip_plan call (#123)."""

    item_ids: list[str] = Field(description="Catalog item ids selected for the trip.")
    gaps: list[Gap] = Field(
        description="Items missing from the catalog this trip needs; [] if none."
    )
    essentials: list[str] = Field(
        description="Packing essentials beyond the catalog, e.g. underwear, sunscreen, charger."
    )
    reasoning: str = Field(description="1-2 sentences explaining the overall pick.")


class PurchaseQuery(BaseModel):
    gap_index: int = Field(..., ge=0)
    query: str = Field(..., min_length=1, max_length=200)
    rationale: str = ""
    used_preferences: list[str] = []


class PurchaseSuggestion(BaseModel):
    gap: Gap
    results: list[PurchaseResult] = []


class TripPlanResponse(BaseModel):
    destination: str
    start_date: date
    end_date: date
    duration_days: int
    weather: TripWeather
    packing_list: list[PackingCategory]
    gaps: list[Gap] = []
    purchase_suggestions: list[PurchaseSuggestion] = []
    reasoning: str = ""
    essentials: list[str] = []


# ---- Saved trip plans (#128) -----------------------------------------------


class TripPlanSaveRequest(BaseModel):
    """Body for POST /trips. `plan` is validated on write; reads return the
    stored blob verbatim (see TripPlanSaved) so the frozen snapshot never
    breaks or silently drops fields as TripPlanResponse evolves."""

    destination: str = Field(..., min_length=1, max_length=200)
    start_date: date
    end_date: date
    notes: str = ""
    plan: TripPlanResponse
    edited: bool = False


class TripPlanSummary(BaseModel):
    """GET /trips list row — scalar fields only, no plan blob."""

    id: str
    created_at: datetime
    destination: str
    start_date: date
    end_date: date
    notes: str = ""
    edited: bool = False


class TripPlanSaved(TripPlanSummary):
    """GET /trips/{id} — the full frozen snapshot, returned as-stored."""

    plan: dict
