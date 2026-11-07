import base64
import time
import uuid

import httpx
import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import Settings, settings
from app.core.rate_limit import _hit_redis
from app.models.token import TokenTransaction, TokenTransactionType
from app.models.user import User
from app.services import receipt_verifier


def test_database_and_redis_urls_escape_credentials():
    configured = Settings(
        SECRET_KEY="development-key",
        POSTGRES_USER="user@example",
        POSTGRES_PASSWORD="p@ss:/#word",
        DATABASE_URL=None,
        GEMINI_API_KEY="test-key",
        ENVIRONMENT="test",
        REDIS_PASSWORD="r@dis:/#word",
    )
    db_url = make_url(configured.ASYNC_DATABASE_URI)
    redis_url = make_url(configured.REDIS_URL)
    assert db_url.password == "p@ss:/#word"
    assert db_url.username == "user@example"
    assert redis_url.password == "r@dis:/#word"
    assert "%40" in configured.ASYNC_DATABASE_URI


@pytest.mark.asyncio
async def test_production_rate_limits_fail_closed_without_redis(monkeypatch):
    from app.core import redis as redis_module
    from fastapi import HTTPException

    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    monkeypatch.setattr(redis_module, "redis_client", None)
    with pytest.raises(HTTPException) as exc:
        await _hit_redis("rl:test:127.0.0.1", 60)
    assert exc.value.status_code == 503


@pytest.mark.asyncio
async def test_admob_callback_credits_once_and_replay_is_idempotent(
    client: httpx.AsyncClient,
    db_session,
    monkeypatch,
):
    login = await client.post(
        "/api/v1/auth/guest-login",
        json={
            "device_id": f"device_{uuid.uuid4().hex[:16]}",
            "device_secret": f"device-secret-{uuid.uuid4().hex}",
        },
    )
    assert login.status_code == 200
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    profile = await client.get("/api/v1/auth/me", headers=headers)
    user_id = profile.json()["id"]

    private_key = ec.generate_private_key(ec.SECP256R1())
    async def trusted_keys():
        return {321: private_key.public_key()}

    monkeypatch.setattr(receipt_verifier, "_get_admob_keys", trusted_keys)
    query = (
        f"ad_network=5450213213286189855&ad_unit=unit-1&reward_amount=1&reward_item=token"
        f"&timestamp={int(time.time() * 1000)}&transaction_id={uuid.uuid4().hex}&user_id={user_id}"
    )
    signature = private_key.sign(query.encode("ascii"), ec.ECDSA(hashes.SHA256()))
    callback = f"{query}&signature={base64.urlsafe_b64encode(signature).decode().rstrip('=')}&key_id=321"

    first = await client.get(f"/api/v1/shop/admob-ssv?{callback}")
    replay = await client.get(f"/api/v1/shop/admob-ssv?{callback}")
    assert first.status_code == replay.status_code == 200
    user = (await db_session.execute(select(User).where(User.id == uuid.UUID(user_id)))).scalar_one()
    assert user.token_balance == 4
    transactions = (await db_session.execute(
        select(TokenTransaction).where(TokenTransaction.transaction_type == TokenTransactionType.REWARDED_AD)
    )).scalars().all()
    assert len(transactions) == 1
