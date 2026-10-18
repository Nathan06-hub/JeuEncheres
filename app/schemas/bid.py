import uuid
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict


class BidSubmitRequest(BaseModel):
    """Screen 03 : Player placing a bid or passing."""
    player_id: uuid.UUID
    amount: int = Field(default=0, ge=0, description="Bid amount or 0 if passing")
    is_pass: bool = Field(default=False, description="Explicit pass action")


class BidResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    player_id: uuid.UUID
    item_id: uuid.UUID
    round_number: int
    clue_level: int
    amount: int
    is_pass: bool
    is_winning_bid: bool
    created_at: datetime


class DraftedItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    session_id: uuid.UUID
    player_id: uuid.UUID
    item_id: uuid.UUID
    winning_bid_amount: int
    clue_level_won: int
    round_number: int
    created_at: datetime
