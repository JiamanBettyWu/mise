from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Formality = Literal["casual", "smart-casual", "formal"]
Season = Literal["spring", "summer", "fall", "winter", "all-season"]

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


# ---- Trip planner ---------------------------------------------------------


class TripPlanRequest(BaseModel):
    destination: str = Field(..., min_length=1, max_length=200)
    start_date: date
    end_date: date
    additional_notes: str = ""


class TripWeatherDay(BaseModel):
    date: date
    high_c: float
    low_c: float
    conditions: str
    precip_chance: float = Field(..., ge=0, le=1)


class TripWeather(BaseModel):
    summary: str
    daily: list[TripWeatherDay] = []


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


class PurchaseSuggestion(BaseModel):
    gap: Gap
    results: list[PurchaseResult] = []