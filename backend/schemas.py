from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Formality = Literal["casual", "smart-casual", "formal"]
Season = Literal["spring", "summer", "fall", "winter", "all-season"]


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
