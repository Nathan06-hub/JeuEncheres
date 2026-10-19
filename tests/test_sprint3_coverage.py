# -*- coding: utf-8 -*-
import asyncio
import json
import uuid
import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.user import User
from app.models.deck import Deck, DeckItem, DeckCategory, ItemRarity
from app.models.game import GameSession, GameStatus
from app.services.timer_manager import timer_manager
from app.services.gemini_service import GeminiService
from app.api.v1.endpoints.creation_ai import (
    _AIItem,
    _validate_ai_items,
    _acquire_generation_lock,
    _release_generation_lock,
)
from app.api.v1.endpoints.auction_ws import (
    auction_websocket,
    create_ws_ticket,
    _error_payload as ws_error_payload,
)
from app.core.exceptions import (
    DomainError,
    ResourceNotFoundError,
    ForbiddenActionError,
    ConflictError,
    InsufficientBalanceError,
    RateLimitExceededError,
)


async def _auth_headers(client: httpx.AsyncClient) -> dict[str, str]:
    d_id = f"dev_{uuid.uuid4().hex[:12]}"
    d_sec = f"device_secret_{uuid.uuid4().hex}"
    resp = await client.post(
        "/api/v1/auth/guest-login",
        json={"device_id": d_id, "device_secret": d_sec},
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


@pytest.mark.asyncio
async def test_auth_register_and_login_flow(client: httpx.AsyncClient):
    """Test complet de /api/v1/auth/register et /api/v1/auth/token."""
    uname = f"player_{uuid.uuid4().hex[:8]}"
    email = f"{uname}@example.com"
    pwd = "StrongPassword123!"

    # 1. Inscription réussie
    reg = await client.post(
        "/api/v1/auth/register",
        json={"username": uname, "email": email, "password": pwd},
    )
    assert reg.status_code == 200, reg.text
    assert reg.json()["username"] == uname
    assert reg.json()["token_balance"] == settings.INITIAL_FREE_TOKENS

    # 2. Doublon rejeté (400)
    dup = await client.post(
        "/api/v1/auth/register",
        json={"username": uname, "email": email, "password": pwd},
    )
    assert dup.status_code == 400

    # 3. Connexion OAuth2 form-data réussie
    tok = await client.post(
        "/api/v1/auth/token",
        data={"username": uname, "password": pwd},
    )
    assert tok.status_code == 200, tok.text
    access_token = tok.json()["access_token"]

    me = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    assert me.status_code == 200
    assert me.json()["email"] == email

    # 4. Mauvais mot de passe et utilisateur inconnu -> 401
    bad_pw = await client.post(
        "/api/v1/auth/token",
        data={"username": uname, "password": "WrongPassword999!"},
    )
    assert bad_pw.status_code == 401

    unknown = await client.post(
        "/api/v1/auth/token",
        data={"username": "no_such_user_xyz", "password": pwd},
    )
    assert unknown.status_code == 401


@pytest.mark.asyncio
async def test_creation_ai_validation_and_generate_endpoint(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Test de /api/v1/creation-ai/suggestions, validation _AIItem et /api/v1/creation-ai/generate."""
    # 1. Chips de suggestions
    sugg = await client.get("/api/v1/creation-ai/suggestions")
    assert sugg.status_code == 200
    assert len(sugg.json()) >= 5

    # 2. Validation unitaire de _AIItem et _validate_ai_items
    coerced = _AIItem.model_validate(
        {"name": "Matrix", "clue_1": "c1", "clue_2": "c2", "clue_3": "c3", "base_score": "85"}
    )
    assert coerced.base_score == 85
    coerced_float = _AIItem.model_validate(
        {"name": "Matrix 2", "clue_1": "c1", "clue_2": "c2", "clue_3": "c3", "base_score": 70.0}
    )
    assert coerced_float.base_score == 70

    with pytest.raises(ValueError):
        _AIItem.model_validate(
            {"name": "Bad", "clue_1": "c1", "clue_2": "c2", "clue_3": "c3", "base_score": True}
        )
    with pytest.raises(ValueError):
        _validate_ai_items("not-a-list", 5)
    with pytest.raises(ValueError):
        _validate_ai_items([{"name": "OnlyOne", "clue_1": "1", "clue_2": "2", "clue_3": "3", "base_score": 50}], 5)

    # 3. Génération complète via l'endpoint avec GeminiService mocké
    headers = await _auth_headers(client)

    async def fake_generate_deck(self, prompt: str, category=None, items_count: int = 5):
        return {
            "title": f"Deck IA {prompt}",
            "description": "Description générée",
            "category": "Cinéma",
            "tags": ["SF", "90s"],
            "items": [
                {
                    "name": f"Objet IA {i}",
                    "clue_1": f"Indice difficile {i}",
                    "clue_2": f"Indice moyen {i}",
                    "clue_3": f"Indice facile {i}",
                    "base_score": 50 + i * 8,
                    "metadata": {"year": 1990 + i},
                }
                for i in range(6)
            ],
        }

    async def fake_get_embedding(self, text: str):
        return [0.01] * 768

    monkeypatch.setattr(GeminiService, "generate_deck", fake_generate_deck)
    monkeypatch.setattr(GeminiService, "get_embedding", fake_get_embedding)

    gen_resp = await client.post(
        "/api/v1/creation-ai/generate",
        headers=headers,
        json={"prompt": "Films SF Cultes", "category": "Cinéma", "items_count": 5},
    )
    assert gen_resp.status_code == 200, gen_resp.text
    deck_json = gen_resp.json()
    assert len(deck_json["items"]) == 5

    from sqlalchemy import select
    created_deck = (
        await db_session.execute(select(Deck).where(Deck.id == uuid.UUID(deck_json["id"])))
    ).scalar_one()
    assert created_deck.is_public is False  # M-10: privé par défaut

    # Le solde de l'utilisateur a été débité de 1 jeton (3 -> 2)
    me = await client.get("/api/v1/auth/me", headers=headers)
    assert me.json()["token_balance"] == settings.INITIAL_FREE_TOKENS - 1

    # 4. Verrou de génération simultanée -> 429
    user_id = uuid.UUID(me.json()["id"])
    ok, tok = await _acquire_generation_lock(user_id)
    assert ok is True
    try:
        locked_resp = await client.post(
            "/api/v1/creation-ai/generate",
            headers=headers,
            json={"prompt": "Second appel concurrent", "items_count": 5},
        )
        assert locked_resp.status_code == 429
    finally:
        await _release_generation_lock(user_id, tok)

    # 5. Plafond global journalier atteint -> 429 sans débiter de jeton
    monkeypatch.setattr(settings, "AI_DAILY_GLOBAL_GENERATION_CAP", 1)
    cap_resp = await client.post(
        "/api/v1/creation-ai/generate",
        headers=headers,
        json={"prompt": "Depassement quota journalier", "items_count": 5},
    )
    assert cap_resp.status_code == 429


@pytest.mark.asyncio
async def test_shop_packs_iap_and_rewarded_ad_flows(
    client: httpx.AsyncClient,
    monkeypatch,
):
    """Test complet de /api/v1/shop/packs, verify-iap, claim-rewarded-ad et transactions."""
    headers = await _auth_headers(client)

    # 1. GET /shop/packs (seed automatique des 3 packs)
    packs_resp = await client.get("/api/v1/shop/packs")
    assert packs_resp.status_code == 200
    packs = packs_resp.json()
    assert len(packs) == 3

    # 2. En mode fail-closed par défaut (ALLOW_UNVERIFIED_PURCHASES=False), verify-iap et rewarded-ad renvoient 501
    monkeypatch.setattr(settings, "ALLOW_UNVERIFIED_PURCHASES", False)
    iap_closed = await client.post(
        "/api/v1/shop/verify-iap",
        headers=headers,
        json={
            "pack_sku": "pack_starter_5",
            "transaction_id": f"tx_{uuid.uuid4().hex[:10]}",
            "receipt_data": "dummy_receipt_payload_data",
            "platform": "ios",
        },
    )
    assert iap_closed.status_code == 501

    ad_closed = await client.post(
        "/api/v1/shop/claim-rewarded-ad",
        headers=headers,
        json={"reward_token": "reward_tok_12345", "ad_network": "AdMob"},
    )
    assert ad_closed.status_code == 501

    # 3. En mode développement avec ALLOW_UNVERIFIED_PURCHASES=True, le crédit et l'idempotence fonctionnent
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")
    monkeypatch.setattr(settings, "ALLOW_UNVERIFIED_PURCHASES", True)

    tx_id = f"tx_dev_{uuid.uuid4().hex[:10]}"
    iap_ok = await client.post(
        "/api/v1/shop/verify-iap",
        headers=headers,
        json={
            "pack_sku": "pack_starter_5",
            "transaction_id": tx_id,
            "receipt_data": "dev_receipt_payload_data",
            "platform": "android",
        },
    )
    assert iap_ok.status_code == 200, iap_ok.text
    assert iap_ok.json()["amount"] == 5

    ad_ok = await client.post(
        "/api/v1/shop/claim-rewarded-ad",
        headers=headers,
        json={"reward_token": f"rw_{uuid.uuid4().hex[:8]}", "ad_network": "AdMob"},
    )
    assert ad_ok.status_code == 200, ad_ok.text
    assert ad_ok.json()["amount"] == 1

    # 4. Historique des transactions
    hist = await client.get("/api/v1/shop/transactions", headers=headers)
    assert hist.status_code == 200
    assert len(hist.json()) >= 3  # INITIAL_GIFT + IAP + REWARDED_AD


@pytest.mark.asyncio
async def test_full_auction_http_lifecycle_and_results(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Cycle complet HTTP : création, démarrage, live-state, enchère, résolution et écran de résultats."""
    monkeypatch.setattr(timer_manager, "start_round_timer", lambda *a, **kw: None)
    monkeypatch.setattr(timer_manager, "cancel_timer", lambda *a, **kw: None)

    headers = await _auth_headers(client)

    deck = Deck(
        title="Deck Cycle Complet",
        slug=f"full-cycle-{uuid.uuid4().hex[:6]}",
        category=DeckCategory.HISTOIRE,
        is_public=True,
    )
    db_session.add(deck)
    await db_session.flush()
    for idx in range(3):
        db_session.add(
            DeckItem(
                deck_id=deck.id,
                name=f"Relique {idx}",
                clue_1=f"Difficile {idx}",
                clue_2=f"Moyen {idx}",
                clue_3=f"Facile {idx}",
                base_score=70 + idx * 10,
                rarity=ItemRarity.EPIC,
                category="Histoire",
            )
        )
    await db_session.commit()

    # Création d'une partie à 3 manches (minimum requis par GameSessionCreate)
    create_resp = await client.post(
        "/api/v1/auction/sessions",
        headers=headers,
        json={
            "deck_id": str(deck.id),
            "player_names": ["Alice", "Bob"],
            "starting_budget": 1000,
            "total_rounds": 3,
            "timer_seconds": 15,
        },
    )
    assert create_resp.status_code == 200
    game_id = create_resp.json()["id"]
    alice_id = create_resp.json()["players"][0]["id"]

    # Résultats indisponibles tant que la partie n'est pas terminée -> 409
    early_res = await client.get(f"/api/v1/results/sessions/{game_id}/results", headers=headers)
    assert early_res.status_code == 409

    # Démarrage
    start_resp = await client.post(f"/api/v1/auction/sessions/{game_id}/start", headers=headers)
    assert start_resp.status_code == 200

    # Live state manche 1
    live1 = await client.get(f"/api/v1/auction/sessions/{game_id}/live-state", headers=headers)
    assert live1.status_code == 200
    assert live1.json()["current_round"] == 1
    assert live1.json()["item"]["revealed_clue_level"] == 1

    # Enchère d'Alice à la manche 1
    bid_resp = await client.post(
        f"/api/v1/auction/sessions/{game_id}/bid",
        headers=headers,
        json={"player_id": alice_id, "amount": 200, "is_pass": False},
    )
    assert bid_resp.status_code == 200

    # Avancer les 3 manches (3 indices chacune = 9 avances) jusqu'à FINISHED
    adv = None
    for rnd in (1, 2, 3):
        for clue in (1, 2, 3):
            adv = await client.post(
                f"/api/v1/auction/sessions/{game_id}/advance",
                headers=headers,
                params={"expected_round": rnd, "expected_clue": clue},
            )
            assert adv.status_code == 200, adv.text
    assert adv is not None and adv.json()["game_finished"] is True

    # Consultation des résultats finaux (1er appel = calcul des rangs, 2e appel = lecture sans écriture)
    res1 = await client.get(f"/api/v1/results/sessions/{game_id}/results", headers=headers)
    assert res1.status_code == 200, res1.text
    data_res = res1.json()
    assert data_res["podium"][0]["display_name"] == "Alice"
    assert len(data_res["compositions"]) == 2

    res2 = await client.get(f"/api/v1/results/sessions/{game_id}/results", headers=headers)
    assert res2.status_code == 200
    assert res2.json()["podium"][0]["player_id"] == data_res["podium"][0]["player_id"]

    # Health & Ready endpoints
    h = await client.get("/health")
    assert h.status_code == 200
    r = await client.get("/ready")
    assert r.status_code in (200, 503)


@pytest.mark.asyncio
async def test_websocket_interactive_actions_and_timer_manager(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Test direct de auction_websocket (ping, sync, start_game, bid, pass) et de timer_manager._timer_loop."""
    headers = await _auth_headers(client)

    deck = Deck(
        title="Deck WS Live",
        slug=f"ws-live-{uuid.uuid4().hex[:6]}",
        category=DeckCategory.POP_CULTURE,
        is_public=True,
    )
    db_session.add(deck)
    await db_session.flush()
    for idx in range(3):
        db_session.add(
            DeckItem(
                deck_id=deck.id,
                name=f"Jeu {idx}",
                clue_1="c1",
                clue_2="c2",
                clue_3="c3",
                base_score=80,
                rarity=ItemRarity.RARE,
            )
        )
    await db_session.commit()

    create_resp = await client.post(
        "/api/v1/auction/sessions",
        headers=headers,
        json={"deck_id": str(deck.id), "player_names": ["HostWS", "GuestWS"], "total_rounds": 3},
    )
    game_id = create_resp.json()["id"]
    host_player_id = create_resp.json()["players"][0]["id"]

    ticket_resp = await client.post("/api/v1/auction/ws-ticket", headers=headers)
    ticket = ticket_resp.json()["ticket"]

    # Fake WebSocket de bout en bout pour piloter auction_websocket dans la même boucle asyncio
    monkeypatch.setattr(timer_manager, "start_round_timer", lambda *a, **kw: None)

    inbox: list[str] = [
        json.dumps({"action": "ping"}),
        json.dumps({"action": "sync"}),
        "not-valid-json",
        "x" * 3000,  # > MAX_MESSAGE_BYTES (413)
        json.dumps({"action": "unknown_cmd"}),
        json.dumps({"action": "start_game"}),
        json.dumps({"action": "bid", "player_id": host_player_id, "amount": 150}),
        json.dumps({"action": "pass", "player_id": host_player_id}),
    ]
    outbox: list[dict] = []

    class _ScriptedWebSocket:
        def __init__(self):
            self.headers = {"sec-websocket-protocol": f"ticket.{ticket}"}
            self.accepted_subprotocol = None
            self.closed_code = None

        async def accept(self, subprotocol=None):
            self.accepted_subprotocol = subprotocol

        async def receive_text(self) -> str:
            if inbox:
                return inbox.pop(0)
            from fastapi import WebSocketDisconnect
            raise WebSocketDisconnect(code=1000)

        async def send_json(self, data: dict):
            outbox.append(data)

        async def send_text(self, text: str):
            outbox.append(json.loads(text))

        async def close(self, code: int = 1000):
            self.closed_code = code

    ws = _ScriptedWebSocket()
    await auction_websocket(ws, session_id=game_id, ticket=None, token=None)

    assert ws.accepted_subprotocol == f"ticket.{ticket}"
    types = [m.get("type") for m in outbox]
    assert "CONNECTED" in types
    assert "STATE_SNAPSHOT" in types
    assert "pong" in types
    assert "GAME_STARTED" in types
    assert "NEW_BID" in types
    assert "PLAYER_PASSED" in types
    error_codes = [m.get("code") for m in outbox if m.get("type") == "ERROR"]
    assert 400 in error_codes
    assert 413 in error_codes

    # Test de _timer_loop (avec duration=0 pour exécution instantanée) et resume_active_games
    resumed = await timer_manager.resume_active_games()
    assert resumed >= 1
    await timer_manager._timer_loop(uuid.UUID(game_id), duration=0, round_number=1, clue_level=1)
    await timer_manager._timer_loop(uuid.UUID(game_id), duration=0, round_number=1, clue_level=2)
    await timer_manager._timer_loop(uuid.UUID(game_id), duration=0, round_number=1, clue_level=3)
    timer_manager.cancel_timer(uuid.UUID(game_id))


def test_domain_exceptions_and_ws_error_payload():
    """Vérifie la hiérarchie DomainError et son formatage WebSocket."""
    err_404 = ResourceNotFoundError("Introuvable")
    err_403 = ForbiddenActionError("Interdit")
    err_409 = ConflictError("Conflit")
    err_400 = InsufficientBalanceError("Solde insuffisant")
    err_402 = DomainError("Paiement requis", status_code=402)
    err_429 = RateLimitExceededError("Trop de requêtes")

    assert isinstance(err_404, DomainError)
    assert ws_error_payload(err_404) == {"type": "ERROR", "code": 404, "message": "Introuvable"}
    assert ws_error_payload(err_403)["code"] == 403
    assert ws_error_payload(err_409)["code"] == 409
    assert ws_error_payload(err_400)["code"] == 400
    assert ws_error_payload(err_402)["code"] == 402
    assert ws_error_payload(err_429)["code"] == 429
    assert ws_error_payload(ValueError("bad"))["code"] == 422
    assert ws_error_payload(RuntimeError("boom"))["code"] == 500


@pytest.mark.asyncio
async def test_sprint4_jwt_strict_claims_refresh_and_csp(client: httpx.AsyncClient):
    """H-02, M-01, M-04 : rejet des JWT sans iss/aud, endpoint /auth/refresh et en-tête CSP."""
    import jwt as pyjwt
    from datetime import datetime, timedelta, timezone
    from fastapi import HTTPException
    from app.api.deps import decode_user_id

    # H-02 : un JWT signé avec la bonne clé mais sans iss ou aud doit être rejeté
    now = datetime.now(timezone.utc)
    token_no_iss = pyjwt.encode(
        {"sub": str(uuid.uuid4()), "exp": now + timedelta(minutes=5), "aud": settings.JWT_AUDIENCE},
        settings.SECRET_KEY,
        algorithm=settings.ALGORITHM,
    )
    with pytest.raises(HTTPException) as exc_info:
        decode_user_id(token_no_iss)
    assert exc_info.value.status_code == 401

    # M-01 : login renvoie refresh_token, utilisable sur POST /api/v1/auth/refresh
    d_id = f"dev_{uuid.uuid4().hex[:12]}"
    d_sec = f"device_secret_{uuid.uuid4().hex}"
    login_resp = await client.post(
        "/api/v1/auth/guest-login",
        json={"device_id": d_id, "device_secret": d_sec},
    )
    assert login_resp.status_code == 200
    tokens = login_resp.json()
    assert tokens.get("refresh_token")

    # M-04 : Content-Security-Policy présent
    assert "default-src 'self'" in login_resp.headers.get("Content-Security-Policy", "")

    refresh_resp = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["refresh_token"]},
    )
    assert refresh_resp.status_code == 200
    assert "access_token" in refresh_resp.json()

    # Un access_token ne peut pas servir de refresh_token -> 401
    bad_refresh = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": tokens["access_token"]},
    )
    assert bad_refresh.status_code == 401


@pytest.mark.asyncio
async def test_sprint5_receipt_verifier_apple_google_and_admob(monkeypatch):
    """H-01 : vérification unitaire de _verify_apple, _verify_google et _verify_ad_ssv."""
    import hashlib
    import hmac
    from fastapi import HTTPException
    from app.services.receipt_verifier import (
        verify_store_receipt,
        verify_rewarded_ad,
    )

    monkeypatch.setattr(settings, "ALLOW_UNVERIFIED_PURCHASES", False)
    monkeypatch.setattr(settings, "APPLE_IAP_BEARER_TOKEN", "apple_test_bearer")
    monkeypatch.setattr(settings, "GOOGLE_PLAY_PACKAGE_NAME", "com.encheres.app")
    monkeypatch.setattr(settings, "GOOGLE_PLAY_ACCESS_TOKEN", "google_test_token")
    monkeypatch.setattr(settings, "ADMOB_SSV_SHARED_SECRET", "admob_secret_key_test")

    class _DummyResponse:
        def __init__(self, status_code: int, payload: dict):
            self.status_code = status_code
            self._payload = payload

        def json(self):
            return self._payload

    responses: list[_DummyResponse] = []

    class _DummyAsyncClient:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            pass

        async def get(self, url: str, headers: dict | None = None):
            return responses.pop(0)

    monkeypatch.setattr(httpx, "AsyncClient", _DummyAsyncClient)

    # 1. Apple IAP : succès (200 + productId correspondant) puis échec (SKU mismatch -> 402)
    responses.append(_DummyResponse(200, {"productId": "pack_starter_5"}))
    await verify_store_receipt("ios", "tx_1", "receipt_abc", "pack_starter_5")

    responses.append(_DummyResponse(200, {"productId": "other_sku"}))
    with pytest.raises(HTTPException) as exc_apple:
        await verify_store_receipt("ios", "tx_2", "receipt_abc", "pack_starter_5")
    assert exc_apple.value.status_code == 402

    # 2. Google Play IAP : succès (purchaseState=0) puis échec (purchaseState=1 -> 402)
    responses.append(_DummyResponse(200, {"purchaseState": 0, "orderId": "gpa_1"}))
    await verify_store_receipt("android", "gpa_1", "tok_xyz", "pack_starter_5")

    responses.append(_DummyResponse(200, {"purchaseState": 1, "orderId": "gpa_2"}))
    with pytest.raises(HTTPException) as exc_google:
        await verify_store_receipt("android", "gpa_2", "tok_xyz", "pack_starter_5")
    assert exc_google.value.status_code == 402

    # Plateforme inconnue -> 400
    with pytest.raises(HTTPException) as exc_plat:
        await verify_store_receipt("windows_phone", "tx_3", "receipt", "pack_starter_5")
    assert exc_plat.value.status_code == 400

    # 3. AdMob SSV : signature HMAC valide vs falsifiée
    uid = str(uuid.uuid4())
    nonce = "nonce12345"
    sig = hmac.new(
        b"admob_secret_key_test",
        f"{uid}:admob:{nonce}".encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    await verify_rewarded_ad(f"{nonce}:{sig}", "AdMob", uid)

    with pytest.raises(HTTPException) as exc_ad:
        await verify_rewarded_ad(f"{nonce}:deadbeef", "AdMob", uid)
    assert exc_ad.value.status_code == 403


@pytest.mark.asyncio
async def test_sprint5_gemini_rate_limit_and_timer_redis_coverage(monkeypatch):
    """M-03 : couverture des branches GeminiService, rate_limit (Redis/mémoire) et timer_manager (bail Redis)."""
    from unittest.mock import AsyncMock, MagicMock
    from fastapi import HTTPException
    from app.core import rate_limit as rl_mod
    from app.core import redis as redis_mod

    # 1. GeminiService avec client mocké (succès, erreur en prod, get_embedding)
    monkeypatch.setattr(settings, "GEMINI_API_KEY", "fake_key_for_unit_test")
    svc = GeminiService()
    mock_client = MagicMock()
    mock_resp = MagicMock()
    mock_resp.text = json.dumps(
        {
            "title": "Deck GenAI",
            "description": "Desc",
            "category": "Cinéma",
            "tags": ["SF"],
            "items": [
                {"name": "Blade Runner", "clue_1": "1", "clue_2": "2", "clue_3": "3", "base_score": 95},
                {"name": "Dune", "clue_1": "1", "clue_2": "2", "clue_3": "3", "base_score": 80},
                {"name": "Alien", "clue_1": "1", "clue_2": "2", "clue_3": "3", "base_score": 60},
                {"name": "Tron", "clue_1": "1", "clue_2": "2", "clue_3": "3", "base_score": 40},
            ],
        }
    )
    mock_client.aio.models.generate_content = AsyncMock(return_value=mock_resp)
    emb_obj = MagicMock()
    emb_obj.values = [0.5] * 768
    mock_emb_resp = MagicMock()
    mock_emb_resp.embeddings = [emb_obj]
    mock_client.aio.models.embed_content = AsyncMock(return_value=mock_emb_resp)
    svc.client = mock_client

    data = await svc.generate_deck("SF 80s", DeckCategory.CINEMA, items_count=4)
    assert data["title"] == "Deck GenAI"
    vec = await svc.get_embedding("Blade Runner")
    assert vec is not None and len(vec) == 768

    # Erreur API en mode production -> lève ValueError
    mock_client.aio.models.generate_content = AsyncMock(side_effect=RuntimeError("API quota"))
    monkeypatch.setattr(settings, "ENVIRONMENT", "production")
    with pytest.raises(ValueError):
        await svc.generate_deck("SF 80s", DeckCategory.CINEMA, items_count=4)
    mock_client.aio.models.embed_content = AsyncMock(side_effect=RuntimeError("Embed error"))
    assert await svc.get_embedding("Blade Runner") is None
    monkeypatch.setattr(settings, "ENVIRONMENT", "development")

    # 2. rate_limit : Lua Redis et éviction mémoire _MAX_MEMORY_KEYS
    fake_redis = MagicMock()
    fake_redis.eval = AsyncMock(return_value=1)
    monkeypatch.setattr(redis_mod, "redis_client", fake_redis)
    assert await rl_mod._hit_redis("rl:test:127.0.0.1", 60) == 1

    fake_redis.eval = AsyncMock(side_effect=RuntimeError("redis down"))
    assert await rl_mod._hit_redis("rl:test:127.0.0.1", 60) is None

    monkeypatch.setattr(rl_mod, "_MAX_MEMORY_KEYS", 2)
    rl_mod._memory_hits.clear()
    rl_mod._hit_memory("k1", 60)
    rl_mod._hit_memory("k2", 60)
    rl_mod._hit_memory("k3", 60)
    assert len(rl_mod._memory_hits) <= 2

    # 3. timer_manager : bail Redis (_acquire_or_renew_lease), _sync_timer_state_to_redis, _timer_loop et cancel_timer
    fake_redis.set = AsyncMock(return_value=True)
    fake_redis.eval = AsyncMock(return_value=1)
    fake_redis.delete = AsyncMock(return_value=1)
    fake_redis.get = AsyncMock(return_value=json.dumps({"round": 99, "clue_level": 1}))
    sid = uuid.uuid4()
    assert await timer_manager._acquire_or_renew_lease(sid, 1, 1, force_takeover=True) is True
    assert await timer_manager._acquire_or_renew_lease(sid, 1, 1, force_takeover=False) is True
    await timer_manager._sync_timer_state_to_redis(sid, 15, 1, 1)
    await timer_manager._timer_loop(sid, 0, 1, 1)
    dummy_task = asyncio.create_task(asyncio.sleep(10))
    timer_manager.running_timers[str(sid)] = dummy_task
    timer_manager.cancel_timer(sid)
    await asyncio.sleep(0)
    monkeypatch.setattr(redis_mod, "redis_client", None)

