from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import get_db
from app.api.deps import get_current_user
from app.models.user import User
from app.models.token import TokenPack, TokenTransaction
from app.schemas.token import (
    TokenPackResponse,
    TokenTransactionResponse,
    IAPReceiptVerificationRequest,
    RewardedAdClaimRequest,
)
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.token import TokenTransactionType
from app.services.receipt_verifier import verify_store_receipt, verify_rewarded_ad
from app.services.token_service import TokenService

router = APIRouter()


DEFAULT_TOKEN_PACKS = (
    {
        "sku": "pack_starter_5",
        "title": "Pack Découverte",
        "tokens_amount": 5,
        "price_cents": 99,
        "currency": "USD",
        "is_best_value": False,
        "badge_text": None,
    },
    {
        "sku": "pack_popular_15",
        "title": "Pack Populaire",
        "tokens_amount": 15,
        "price_cents": 249,
        "currency": "USD",
        "is_best_value": True,
        "badge_text": "Meilleure Valeur",
    },
    {
        "sku": "pack_pro_50",
        "title": "Pack Maître",
        "tokens_amount": 50,
        "price_cents": 699,
        "currency": "USD",
        "is_best_value": False,
        "badge_text": "Gros Volume",
    },
)


async def seed_default_token_packs(session: AsyncSession) -> None:
    """Initialise de manière idempotente le catalogue des packs de jetons au démarrage."""
    res = await session.execute(select(TokenPack.sku))
    existing_skus = set(res.scalars().all())
    missing = [TokenPack(**p) for p in DEFAULT_TOKEN_PACKS if p["sku"] not in existing_skus]
    if not missing:
        return
    session.add_all(missing)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()


@router.get("/packs", response_model=List[TokenPackResponse], summary="📱 Écran 05 : Grille des packs de jetons payants ($0.99, $2.49, $6.99)")
async def get_token_packs(session: AsyncSession = Depends(get_db)) -> Any:
    """Catalogue des packs disponibles avec badges 'Meilleure Valeur' (lecture pure sans écriture)."""
    query = select(TokenPack).where(TokenPack.is_active.is_(True)).order_by(TokenPack.price_cents.asc())
    res = await session.execute(query)
    return list(res.scalars().all())


@router.post("/verify-iap", response_model=TokenTransactionResponse, summary="📱 Écran 05 : Validation d'achat In-App et attribution de jetons")
async def verify_iap(
    payload: IAPReceiptVerificationRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    await verify_store_receipt(
        platform=payload.platform,
        transaction_id=payload.transaction_id,
        receipt_data=payload.receipt_data,
        pack_sku=payload.pack_sku,
    )
    tx = await TokenService.process_iap_purchase(
        session=session,
        user_id=current_user.id,
        pack_sku=payload.pack_sku,
        transaction_id=payload.transaction_id,
        platform=payload.platform,
    )
    await session.commit()
    await session.refresh(tx)
    return tx


@router.post("/claim-rewarded-ad", response_model=TokenTransactionResponse, summary="📱 Écran 05 : Attribution de +1 jeton gratuit via vidéo publicitaire")
async def claim_rewarded_ad(
    payload: RewardedAdClaimRequest,
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    await verify_rewarded_ad(payload.reward_token, payload.ad_network, str(current_user.id))

    tx = await TokenService.claim_rewarded_ad(
        session=session,
        user_id=current_user.id,
        reward_token=payload.reward_token,
        ad_network=payload.ad_network,
    )
    await session.commit()
    await session.refresh(tx)
    return tx


@router.get("/transactions", response_model=List[TokenTransactionResponse], summary="📱 Écran 05 : Historique des transactions et achats")
async def get_transaction_history(
    current_user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Any:
    query = (
        select(TokenTransaction)
        .where(TokenTransaction.user_id == current_user.id)
        .order_by(TokenTransaction.created_at.desc())
        .limit(50)
    )
    res = await session.execute(query)
    return res.scalars().all()
