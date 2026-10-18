import pytest
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.token import TokenPack, TokenTransaction, TokenTransactionType
from app.models.user import User
from app.services.token_service import TokenService


async def _make_user(db: AsyncSession, balance: int = 3) -> User:
    user = User(username=f"user_{balance}_{id(db)}", token_balance=balance)
    db.add(user)
    await db.flush()
    return user


@pytest.mark.asyncio
async def test_iap_replay_is_rejected_with_409_and_balance_unchanged(db_session: AsyncSession):
    user = await _make_user(db_session, balance=3)
    db_session.add(
        TokenPack(sku="pack_test", title="Pack", tokens_amount=15, price_cents=249, currency="USD")
    )
    await db_session.flush()

    await TokenService.process_iap_purchase(db_session, user.id, "pack_test", "RECEIPT-1", "ios")
    assert user.token_balance == 18

    with pytest.raises(HTTPException) as exc:
        await TokenService.process_iap_purchase(db_session, user.id, "pack_test", "RECEIPT-1", "ios")
    assert exc.value.status_code == 409
    assert exc.value.detail == "Transaction déjà traitée"

    # Le solde n'a pas bougé et un seul crédit existe au grand livre
    await db_session.refresh(user)
    assert user.token_balance == 18
    rows = (
        await db_session.execute(
            select(TokenTransaction).where(
                TokenTransaction.user_id == user.id,
                TokenTransaction.reference_id == "RECEIPT-1",
            )
        )
    ).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_distinct_receipts_and_debits_are_not_blocked(db_session: AsyncSession):
    user = await _make_user(db_session, balance=5)

    await TokenService.claim_rewarded_ad(db_session, user.id, "AD-1", "admob")
    await TokenService.claim_rewarded_ad(db_session, user.id, "AD-2", "admob")
    # Deux débits (reference_id NULL) ne doivent pas entrer en conflit
    await TokenService.deduct_deck_creation_token(db_session, user.id, "Sujet A")
    await TokenService.deduct_deck_creation_token(db_session, user.id, "Sujet B")

    assert user.token_balance == 5 + 2 - 2


@pytest.mark.asyncio
async def test_same_reference_allowed_across_different_transaction_types(db_session: AsyncSession):
    user = await _make_user(db_session, balance=1)
    await TokenService.modify_token_balance(
        db_session, user.id, 1, TokenTransactionType.REWARDED_AD, reference_id="X"
    )
    await TokenService.modify_token_balance(
        db_session, user.id, 1, TokenTransactionType.IAP_PURCHASE, reference_id="X"
    )
    assert user.token_balance == 3


@pytest.mark.asyncio
async def test_insufficient_balance_is_rejected(db_session: AsyncSession):
    user = await _make_user(db_session, balance=0)
    with pytest.raises(HTTPException) as exc:
        await TokenService.deduct_deck_creation_token(db_session, user.id, "Sujet")
    assert exc.value.status_code == 400
