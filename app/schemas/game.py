import uuid
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict
from app.models.game import GameMode, GameStatus
from app.schemas.deck import DeckItemLiveAuctionView, DeckItemResponse


class GameSessionCreate(BaseModel):
    deck_id: uuid.UUID
    mode: GameMode = GameMode.LOCAL_PASS_AND_PLAY
    total_rounds: int = Field(default=10, ge=3, le=20)
    starting_budget: int = Field(default=1000, ge=100, le=10000)
    timer_seconds: int = Field(default=15, ge=5, le=60)
    player_names: List[str] = Field(..., min_length=1, max_length=8, description="Player/guest names")


class GameSessionPlayerResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    user_id: Optional[uuid.UUID] = None
    display_name: str
    avatar_url: Optional[str] = None
    remaining_budget: int
    base_score_total: int
    synergy_bonus: int
    final_score: int
    roi_percentage: float
    rank: Optional[int] = None
    is_host: bool
    is_bot: bool
    is_ready: bool


class GameSessionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    deck_id: uuid.UUID
    mode: GameMode
    status: GameStatus
    starting_budget: int
    total_rounds: int
    current_round: int
    current_clue_level: int
    timer_seconds: int
    round_deadline: Optional[datetime] = None
    started_at: Optional[datetime] = None
    ended_at: Optional[datetime] = None
    players: List[GameSessionPlayerResponse] = Field(default_factory=list)


class PlayerDraftComposition(BaseModel):
    """Screen 04 : Team Composition with won cards and triggered synergies."""
    player_id: uuid.UUID
    display_name: str
    avatar_url: Optional[str] = None
    remaining_budget: int
    spent_budget: int
    base_score_total: int
    synergy_bonus: int
    final_score: int
    roi_percentage: float
    rank: int
    items: List[Dict[str, Any]] = Field(default_factory=list)
    synergies_breakdown: List[Dict[str, Any]] = Field(default_factory=list)


class PodiumEntry(BaseModel):
    player_id: uuid.UUID
    display_name: str
    rank: int
    final_score: int
    roi_percentage: float
    remaining_budget: int


class GameResultsResponse(BaseModel):
    """Screen 04 : Results and Composition final report."""
    session_id: uuid.UUID
    deck_title: str
    total_rounds: int
    podium: List[PodiumEntry]
    compositions: List[PlayerDraftComposition]
