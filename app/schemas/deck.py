import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.deck import DeckCategory, ItemRarity


class DeckItemBase(BaseModel):
    name: str = Field(..., max_length=180)
    clue_1: str = Field(..., description="Subtle clue")
    clue_2: str = Field(..., description="Intermediate clue")
    clue_3: str = Field(..., description="Revealing clue")
    base_score: int = Field(..., ge=1, le=100, description="Prestige note 1-100")
    rarity: ItemRarity
    category: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None


class DeckItemCreate(DeckItemBase):
    embedding: Optional[List[float]] = None


class DeckItemResponse(DeckItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    created_at: datetime


class DeckItemLiveAuctionView(BaseModel):
    """Item representation during live auction where clues are progressively revealed."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    deck_id: uuid.UUID
    category: Optional[str] = None
    clue_1: str
    clue_2: Optional[str] = None
    clue_3: Optional[str] = None
    revealed_clue_level: int
    name_hidden: bool = True
    base_score_hidden: bool = True


class DeckBase(BaseModel):
    title: str = Field(..., max_length=150)
    description: str = ""
    category: DeckCategory
    tags: List[str] = Field(default_factory=list)
    is_public: bool = True


class DeckGenerateRequest(BaseModel):
    """Screen 02 : Free text prompt for AI deck generation."""
    prompt: str = Field(..., min_length=3, max_length=200, description="e.g. 'Films de SF des années 90'")
    category: Optional[DeckCategory] = None
    items_count: int = Field(default=10, ge=5, le=20, description="Number of items to generate")


class DeckSummaryResponse(BaseModel):
    """Screen 01 : Compact deck card for home screen feed & chips."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    slug: str
    description: str
    category: DeckCategory
    tags: List[str]
    is_official: bool
    play_count: int
    likes_count: int
    items_count: Optional[int] = None
    created_at: datetime


class DeckDetailResponse(DeckSummaryResponse):
    """Full deck with all cards."""
    creator_id: Optional[uuid.UUID] = None
    ai_prompt: Optional[str] = None
    items: List[DeckItemResponse] = Field(default_factory=list)
