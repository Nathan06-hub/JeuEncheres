from typing import Any, List
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, status
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
)
from datetime import datetime, timedelta, timezone
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.token import TokenTransactionType
from app.services.receipt_verifier import (
    consume_google_purchase,
    verify_admob_callback,
    verify_store_receipt,
)
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
    try:
        tx = await TokenService.process_iap_purchase(
            session=session,
            user_id=current_user.id,
            pack_sku=payload.pack_sku,
            transaction_id=payload.transaction_id,
            platform=payload.platform,
        )
    except HTTPException as exc:
        if exc.status_code == status.HTTP_409_CONFLICT and payload.platform.lower() in ("google", "android"):
            await consume_google_purchase(payload.pack_sku, payload.receipt_data)
        raise
    await session.commit()
    await session.refresh(tx)
    if payload.platform.lower() in ("google", "android"):
        await consume_google_purchase(payload.pack_sku, payload.receipt_data)
    return tx


@router.get("/admob-ssv", summary="Callback serveur AdMob SSV signé")
async def admob_ssv_callback(
    request: Request,
    session: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    claims = await verify_admob_callback(request.scope.get("query_string", b""))
    user_id = UUID(claims["user_id"])
    existing = (await session.execute(
        select(TokenTransaction).where(
            TokenTransaction.transaction_type == TokenTransactionType.REWARDED_AD,
            TokenTransaction.reference_id == claims["transaction_id"],
        )
    )).scalar_one_or_none()
    if existing:
        if existing.user_id != user_id:
            raise HTTPException(status.HTTP_409_CONFLICT, "Transaction publicitaire déjà attribuée")
        return {"ok": True}

    try:
        await TokenService.claim_rewarded_ad(
            session=session,
            user_id=user_id,
            reward_token=claims["transaction_id"],
            ad_network="admob",
        )
        await session.commit()
    except HTTPException as exc:
        if exc.status_code != status.HTTP_409_CONFLICT:
            raise
        await session.rollback()
        existing = (await session.execute(
            select(TokenTransaction).where(
                TokenTransaction.transaction_type == TokenTransactionType.REWARDED_AD,
                TokenTransaction.reference_id == claims["transaction_id"],
            )
        )).scalar_one_or_none()
        if not existing or existing.user_id != user_id:
            raise
    return {"ok": True}


@router.post("/claim-rewarded-ad", include_in_schema=False)
async def claim_rewarded_ad_client_disabled() -> None:
    raise HTTPException(
        status_code=status.HTTP_410_GONE,
        detail="Les crédits publicitaires sont attribués par le callback serveur AdMob.",
    )


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
