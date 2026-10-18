"""Pydantic schemas registry."""
from app.schemas.common import APIResponse, PaginatedResponse
from app.schemas.user import (
    UserBase,
    UserCreate,
    UserLogin,
    UserGuestLogin,
    UserResponse,
    UserTokenBalance,
    Token,
)
from app.schemas.token import (
    TokenTransactionResponse,
    TokenPackResponse,
    IAPReceiptVerificationRequest,
    RewardedAdClaimRequest,
)
from app.schemas.deck import (
    DeckItemBase,
    DeckItemCreate,
    DeckItemResponse,
    DeckItemLiveAuctionView,
    DeckBase,
    DeckGenerateRequest,
    DeckSummaryResponse,
    DeckDetailResponse,
)
from app.schemas.game import (
    GameSessionCreate,
    GameSessionResponse,
    GameSessionPlayerResponse,
    PlayerDraftComposition,
    GameResultsResponse,
)
from app.schemas.bid import (
    BidSubmitRequest,
    BidResponse,
    DraftedItemResponse,
)

__all__ = [
    "APIResponse",
    "PaginatedResponse",
    "UserBase",
    "UserCreate",
    "UserLogin",
    "UserGuestLogin",
    "UserResponse",
    "UserTokenBalance",
    "Token",
    "TokenTransactionResponse",
    "TokenPackResponse",
    "IAPReceiptVerificationRequest",
    "RewardedAdClaimRequest",
    "DeckItemBase",
    "DeckItemCreate",
    "DeckItemResponse",
    "DeckItemLiveAuctionView",
    "DeckBase",
    "DeckGenerateRequest",
    "DeckSummaryResponse",
    "DeckDetailResponse",
    "GameSessionCreate",
    "GameSessionResponse",
    "GameSessionPlayerResponse",
    "PlayerDraftComposition",
    "GameResultsResponse",
    "BidSubmitRequest",
    "BidResponse",
    "DraftedItemResponse",
]
