import uuid
from typing import Optional, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from fastapi import HTTPException, status

from app.core.config import settings

from app.models.user import User
from app.models.token import TokenTransaction, TokenTransactionType, TokenPack


class TokenService:
    """Service managing atomic token transactions, balances, IAP, and Ad rewards."""

    @staticmethod
    async def get_user_balance(session: AsyncSession, user_id: uuid.UUID) -> int:
        query = select(User.token_balance).where(User.id == user_id)
        result = await session.execute(query)
        balance = result.scalar_one_or_none()
        if balance is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )
        return balance

    @staticmethod
    async def modify_token_balance(
        session: AsyncSession,
        user_id: uuid.UUID,
        amount: int,
        transaction_type: TokenTransactionType,
        reference_id: Optional[str] = None,
        metadata_json: Optional[Dict[str, Any]] = None,
    ) -> TokenTransaction:
        """Atomically debit or credit tokens from user balance with transaction ledger log."""
        # Lock user row for update to prevent race conditions
        query = select(User).where(User.id == user_id).with_for_update()
        result = await session.execute(query)
        user = result.scalar_one_or_none()

        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        new_balance = user.token_balance + amount
        if new_balance < 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Solde de jetons insuffisant (Requis: {abs(amount)}, Actuel: {user.token_balance})",
            )

        tx = TokenTransaction(
            user_id=user_id,
            amount=amount,
            balance_after=new_balance,
            transaction_type=transaction_type,
            reference_id=reference_id,
            metadata_json=metadata_json or {},
        )

        # L'écriture du grand livre est faite AVANT la mise à jour du solde, dans un SAVEPOINT :
        # si l'index unique (transaction_type, reference_id) est violé (reçu IAP / reward déjà
        # traité), seul le savepoint est annulé et le solde de la session n'a pas été modifié.
        try:
            async with session.begin_nested():
                session.add(tx)
                await session.flush()
        except IntegrityError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Transaction déjà traitée",
            )

        user.token_balance = new_balance
        await session.flush()
        return tx

    @classmethod
    async def deduct_deck_creation_token(
        cls,
        session: AsyncSession,
        user_id: uuid.UUID,
        deck_title: str,
    ) -> TokenTransaction:
        """Deduct 1 token for AI deck creation."""
        return await cls.modify_token_balance(
            session=session,
            user_id=user_id,
            amount=-settings.AI_DECK_CREATION_TOKEN_COST,
            transaction_type=TokenTransactionType.AI_DECK_CREATION,
            metadata_json={"deck_title": deck_title},
        )

    @classmethod
    async def process_iap_purchase(
        cls,
        session: AsyncSession,
        user_id: uuid.UUID,
        pack_sku: str,
        transaction_id: str,
        platform: str,
    ) -> TokenTransaction:
        """Process validated store purchase and grant tokens."""
        pack_query = select(TokenPack).where(TokenPack.sku == pack_sku, TokenPack.is_active.is_(True))
        pack_res = await session.execute(pack_query)
        pack = pack_res.scalar_one_or_none()

        if not pack:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Pack de jetons introuvable",
            )

        return await cls.modify_token_balance(
            session=session,
            user_id=user_id,
            amount=pack.tokens_amount,
            transaction_type=TokenTransactionType.IAP_PURCHASE,
            reference_id=transaction_id,
            metadata_json={
                "pack_sku": pack.sku,
                "price_cents": pack.price_cents,
                "currency": pack.currency,
                "platform": platform,
            },
        )

    @classmethod
    async def claim_rewarded_ad(
        cls,
        session: AsyncSession,
        user_id: uuid.UUID,
        reward_token: str,
        ad_network: str,
    ) -> TokenTransaction:
        """Credit 1 free token after rewarded video ad."""
        return await cls.modify_token_balance(
            session=session,
            user_id=user_id,
            amount=1,
            transaction_type=TokenTransactionType.REWARDED_AD,
            reference_id=reward_token,
            metadata_json={"ad_network": ad_network},
        )
