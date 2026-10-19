# -*- coding: utf-8 -*-
import uuid
import pytest
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.user import User
from app.models.deck import Deck, DeckItem, DeckCategory, ItemRarity
from app.models.game import GameSession, GameStatus, GameSessionPlayer
from app.services.timer_manager import timer_manager


async def _get_auth_headers(client: httpx.AsyncClient, device_id: str | None = None) -> dict:
    d_id = device_id or f"dev_{uuid.uuid4().hex[:12]}"
    d_sec = f"device_secret_{uuid.uuid4().hex}"
    resp = await client.post(
        "/api/v1/auth/guest-login",
        json={"device_id": d_id, "device_secret": d_sec},
    )
    assert resp.status_code == 200, resp.text
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_guest_login_creation_and_persistence(client: httpx.AsyncClient):
    """Scenario 1: POST /api/v1/auth/guest-login creation et persistance session invite."""
    dev_id = f"test_device_{uuid.uuid4().hex[:8]}"
    dev_secret = f"my_secure_device_secret_{uuid.uuid4().hex}"

    # 1. Premier login : creation du compte invite avec solde initial
    resp1 = await client.post(
        "/api/v1/auth/guest-login",
        json={"device_id": dev_id, "device_secret": dev_secret},
    )
    assert resp1.status_code == 200, resp1.text
    data1 = resp1.json()
    assert "access_token" in data1
    assert data1["token_type"] == "bearer"

    token = data1["access_token"]
    me_resp = await client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_resp.status_code == 200
    user_data = me_resp.json()
    assert user_data["token_balance"] >= 3

    # 2. Re-connexion avec le meme device_id et device_secret : persistance du compte
    resp2 = await client.post(
        "/api/v1/auth/guest-login",
        json={"device_id": dev_id, "device_secret": dev_secret},
    )
    assert resp2.status_code == 200
    token2 = resp2.json()["access_token"]
    me_resp2 = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token2}"},
    )
    assert me_resp2.status_code == 200
    assert me_resp2.json()["id"] == user_data["id"]

    # 3. Rejet si mauvais secret presente (>= 32 chars)
    bad_resp = await client.post(
        "/api/v1/auth/guest-login",
        json={"device_id": dev_id, "device_secret": "wrong_secret_12345678901234567890123456"},
    )
    assert bad_resp.status_code == 401


@pytest.mark.asyncio
async def test_create_session_and_quick_game_response_schema(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch,
):
    """Scenario 2: Verification de GameSessionResponse complet avec liste des joueurs sans MissingGreenlet."""
    monkeypatch.setattr(timer_manager, "start_round_timer", lambda *a, **kw: None)
    headers = await _get_auth_headers(client)

    deck = Deck(title="Deck Test API", slug=f"deck-test-{uuid.uuid4().hex[:6]}", category=DeckCategory.CINEMA, is_public=True)
    db_session.add(deck)
    await db_session.flush()

    for idx in range(5):
        it = DeckItem(
            deck_id=deck.id,
            name=f"Film {idx}",
            clue_1=f"c1_{idx}",
            clue_2=f"c2_{idx}",
            clue_3=f"c3_{idx}",
            base_score=60 + idx,
            rarity=ItemRarity.RARE,
            category="Cinema",
        )
        db_session.add(it)
    await db_session.commit()

    # 1. POST /api/v1/auction/sessions
    resp_create = await client.post(
        "/api/v1/auction/sessions",
        headers=headers,
        json={
            "deck_id": str(deck.id),
            "player_names": ["HostPlayer", "Player2"],
            "starting_budget": 1000,
            "total_rounds": 5,
            "timer_seconds": 15,
        },
    )
    assert resp_create.status_code == 200, resp_create.text
    session_data = resp_create.json()
    assert session_data["status"] == "LOBBY"
    assert "players" in session_data
    assert len(session_data["players"]) == 2
    assert session_data["players"][0]["display_name"] == "HostPlayer"
    assert session_data["players"][1]["display_name"] == "Player2"

    # 2. POST /api/v1/auction/quick-game
    resp_quick = await client.post(
        "/api/v1/auction/quick-game",
        headers=headers,
        params={"deck_id": str(deck.id)},
    )
    assert resp_quick.status_code == 200, resp_quick.text
    quick_data = resp_quick.json()
    assert quick_data["status"] == "ROUND_BIDDING"
    assert "players" in quick_data
    assert len(quick_data["players"]) == 3


@pytest.mark.asyncio
async def test_join_session_rules(client: httpx.AsyncClient, db_session: AsyncSession):
    """Scenario 3: Verification des regles de statut et limitation a 8 joueurs."""
    host_headers = await _get_auth_headers(client)

    deck = Deck(title="Join Deck", slug=f"join-deck-{uuid.uuid4().hex[:6]}", category=DeckCategory.SPORT, is_public=True)
    db_session.add(deck)
    await db_session.flush()

    for idx in range(3):
        it = DeckItem(deck_id=deck.id, name=f"Sport {idx}", clue_1="1", clue_2="2", clue_3="3", base_score=50, rarity=ItemRarity.COMMON)
        db_session.add(it)
    await db_session.commit()

    # Creer une session en attente
    resp = await client.post(
        "/api/v1/auction/sessions",
        headers=host_headers,
        json={"deck_id": str(deck.id), "player_names": ["Host"], "total_rounds": 3},
    )
    game_id = resp.json()["id"]

    # Joueur 2 rejoint avec succes via /sessions/{id}/join
    p2_headers = await _get_auth_headers(client)
    join_resp = await client.post(f"/api/v1/auction/sessions/{game_id}/join", headers=p2_headers)
    assert join_resp.status_code == 200
    assert len(join_resp.json()["players"]) == 2

    # Lancer la partie
    start_resp = await client.post(f"/api/v1/auction/sessions/{game_id}/start", headers=host_headers)
    assert start_resp.status_code == 200

    # Joueur 3 tente de rejoindre apres lancement : rejet 400
    p3_headers = await _get_auth_headers(client)
    late_join_resp = await client.post(f"/api/v1/auction/sessions/{game_id}/join", headers=p3_headers)
    assert late_join_resp.status_code == 400
    assert "commencé" in late_join_resp.json()["detail"].lower() or "commence" in late_join_resp.json()["detail"].lower()

    # Tester la limitation a 8 joueurs dans une session WAITING
    resp_limit = await client.post(
        "/api/v1/auction/sessions",
        headers=host_headers,
        json={"deck_id": str(deck.id), "player_names": [f"P{i}" for i in range(8)], "total_rounds": 3},
    )
    full_game_id = resp_limit.json()["id"]
    over_join_resp = await client.post(f"/api/v1/auction/sessions/{full_game_id}/join", headers=p3_headers)
    assert over_join_resp.status_code == 400
    assert "complet" in over_join_resp.json()["detail"].lower()


@pytest.mark.asyncio
async def test_ws_ticket_generation(client: httpx.AsyncClient):
    """Scenario 4: POST /api/v1/auction/ws-ticket creation et statut HTTP 200."""
    headers = await _get_auth_headers(client)

    resp = await client.post("/api/v1/auction/ws-ticket", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert "ticket" in data
    assert data["ticket"].startswith("wst_")
    assert data["expires_in"] == 60


@pytest.mark.asyncio
async def test_get_home_structures(client: httpx.AsyncClient, db_session: AsyncSession):
    """Scenario 5: GET /api/v1/home et validation des structures retournees."""
    headers = await _get_auth_headers(client)

    deck = Deck(title="Deck Home Public", slug=f"home-{uuid.uuid4().hex[:6]}", category=DeckCategory.HISTOIRE, is_public=True, play_count=10)
    db_session.add(deck)
    await db_session.commit()

    # 1. GET /api/v1/home
    resp_home = await client.get("/api/v1/home", headers=headers)
    assert resp_home.status_code == 200
    home_data = resp_home.json()
    assert home_data["is_authenticated"] is True
    assert "user_balance" in home_data
    assert "categories" in home_data
    assert "popular_decks" in home_data
    assert isinstance(home_data["popular_decks"], list)

    # 2. GET /api/v1/home/summary
    resp_summary = await client.get("/api/v1/home/summary")
    assert resp_summary.status_code == 200
    summary_data = resp_summary.json()
    assert summary_data["is_authenticated"] is False
    assert "categories" in summary_data

    # 3. GET /api/v1/home/decks/popular
    resp_pop = await client.get("/api/v1/home/decks/popular")
    assert resp_pop.status_code == 200
    assert isinstance(resp_pop.json(), list)
    assert resp_pop.headers.get("X-Content-Type-Options") == "nosniff"
    assert resp_pop.headers.get("X-Frame-Options") == "DENY"
    assert "X-Request-ID" in resp_pop.headers


@pytest.mark.asyncio
async def test_legacy_guest_without_secret_is_rejected(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """M-01: Un compte invite herite sans device_secret_hash ne doit pas adopter le premier secret presente."""
    legacy_dev_id = f"legacy_dev_{uuid.uuid4().hex[:10]}"
    legacy_user = User(
        device_id=legacy_dev_id,
        device_secret_hash=None,
        username=f"legacy_{uuid.uuid4().hex[:6]}",
        token_balance=3,
    )
    db_session.add(legacy_user)
    await db_session.commit()

    resp = await client.post(
        "/api/v1/auth/guest-login",
        json={
            "device_id": legacy_dev_id,
            "device_secret": "attacker_secret_123456789012345678901234",
        },
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_private_deck_idor_protection_on_create_session(
    client: httpx.AsyncClient,
    db_session: AsyncSession,
):
    """M-03: Impossible de creer une salle sur le deck prive d'un autre utilisateur."""
    owner = User(username=f"owner_{uuid.uuid4().hex[:6]}", token_balance=3)
    db_session.add(owner)
    await db_session.flush()

    private_deck = Deck(
        creator_id=owner.id,
        title="Secret Private Deck",
        slug=f"priv-{uuid.uuid4().hex[:8]}",
        category=DeckCategory.CINEMA,
        is_public=False,
    )
    db_session.add(private_deck)
    await db_session.flush()
    db_session.add(
        DeckItem(
            deck_id=private_deck.id,
            name="Secret Item",
            clue_1="c1",
            clue_2="c2",
            clue_3="c3",
            base_score=80,
            rarity=ItemRarity.EPIC,
        )
    )
    await db_session.commit()

    other_headers = await _get_auth_headers(client)
    resp = await client.post(
        "/api/v1/auction/sessions",
        headers=other_headers,
        json={"deck_id": str(private_deck.id), "player_names": ["Attacker"]},
    )
    assert resp.status_code == 403


