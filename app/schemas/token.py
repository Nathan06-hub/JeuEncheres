import uuid
from datetime import datetime
from typing import Optional, Dict, Any, List, Literal
from pydantic import BaseModel, Field, ConfigDict
from app.models.token import TokenTransactionType


class TokenTransactionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    amount: int
    balance_after: int
    transaction_type: TokenTransactionType
    reference_id: Optional[str] = None
    metadata_json: Optional[Dict[str, Any]] = None
    created_at: datetime


class TokenPackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    sku: str
    title: str
    tokens_amount: int
    price_cents: int
    currency: str
    is_best_value: bool
    badge_text: Optional[str] = None
    is_active: bool


class IAPReceiptVerificationRequest(BaseModel):
    pack_sku: str = Field(..., min_length=1, max_length=64, description="SKU of the purchased pack")
    platform: Literal["apple", "google", "ios", "android"] = Field(..., description="'apple' or 'google'")
    receipt_data: str = Field(..., min_length=1, max_length=16384, description="Encrypted receipt payload or token")
    transaction_id: str = Field(..., min_length=1, max_length=255, description="Store transaction identifier")


class RewardedAdClaimRequest(BaseModel):
    ad_network: str = Field(default="admob", min_length=1, max_length=64, description="Ad network name")
    reward_token: str = Field(..., min_length=1, max_length=255, description="Server-to-server or cryptographic reward verification token")
