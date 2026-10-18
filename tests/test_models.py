import pytest
import uuid
from unittest.mock import AsyncMock, MagicMock
from app.models.user import User
from app.models.token import TokenTransaction, TokenTransactionType, TokenPack
from app.models.deck import Deck, DeckItem, DeckCategory, ItemRarity
from app.models.game import GameSession, GameSessionPlayer, GameMode, GameStatus
from app.models.bid import Bid, DraftedItem
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.database import get_db
from app.main import app


def test_password_hashing():
    pw = "SecretP@ssw0rd!"
    hashed = get_password_hash(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword", hashed) is False


def test_jwt_token_generation():
    user_id = uuid.uuid4()
    token = create_access_token(subject=str(user_id))
    assert isinstance(token, str)
    assert len(token) > 20


def test_user_and_token_models():
    user_id = uuid.uuid4()
    user = User(
        id=user_id,
        device_id="device_iphone_15_pro_xyz",
        username="player_one",
        email="player@example.com",
        token_balance=3,
        is_active=True,
    )
    assert user.token_balance == 3
    assert user.is_active is True

    tx = TokenTransaction(
        user_id=user.id,
        amount=-1,
        balance_after=2,
        transaction_type=TokenTransactionType.AI_DECK_CREATION,
    )
    assert tx.amount == -1
    assert tx.balance_after == 2
    assert tx.transaction_type == TokenTransactionType.AI_DECK_CREATION


def test_deck_and_item_clues():
    deck_id = uuid.uuid4()
    deck = Deck(
        id=deck_id,
        title="Science-Fiction Culte",
        slug="science-fiction-culte",
        category=DeckCategory.CINEMA,
        is_official=True,
    )
    assert deck.category == DeckCategory.CINEMA

    item = DeckItem(
        deck_id=deck.id,
        name="Blade Runner",
        clue_1="Des larmes sous la pluie et un test d'empathie.",
        clue_2="Los Angeles en 2019 dans une dystopie cyberpunk signée Ridley Scott.",
        clue_3="Harrison Ford traque les réplicants menés par Roy Batty.",
        base_score=94,
        rarity=ItemRarity.LEGENDARY,
    )
    assert item.base_score == 94
    assert item.rarity == ItemRarity.LEGENDARY
    assert item.clue_1 != ""
    assert item.clue_2 != ""
    assert item.clue_3 != ""


def test_game_session_and_bid_structure():
    session_id = uuid.uuid4()
    player_id = uuid.uuid4()
    item_id = uuid.uuid4()

    game = GameSession(
        id=session_id,
        code="GAME01",
        deck_id=uuid.uuid4(),
        status=GameStatus.ROUND_BIDDING,
        starting_budget=1000,
        current_round=1,
        current_clue_level=1,
    )
    assert game.starting_budget == 1000
    assert game.current_clue_level == 1

    bid = Bid(
        session_id=session_id,
        player_id=player_id,
        item_id=item_id,
        round_number=1,
        clue_level=1,
        amount=150,
        is_pass=False,
    )
    assert bid.amount == 150
    assert bid.clue_level == 1
    assert bid.is_pass is False


@pytest.mark.asyncio
async def test_api_health_endpoint(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded", "unhealthy")  # /health = liveness, l'état des dépendances est dans `checks``n    assert set(data["checks"]) == {"postgres", "redis"}
    assert "version" in data


@pytest.mark.asyncio
async def test_api_suggestions_endpoint(client):
    response = await client.get("/api/v1/creation-ai/suggestions")
    assert response.status_code == 200
    suggestions = response.json()
    assert isinstance(suggestions, list)
    assert len(suggestions) > 0
    assert "Films de SF des années 90" in suggestions


@pytest.mark.asyncio
async def test_api_home_summary_unauth(client):
    # Mock DB dependency for testing without live Postgres
    mock_session = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar.return_value = 5  # 5 active games
    mock_session.execute.return_value = mock_result

    async def override_get_db():
        yield mock_session

    app.dependency_overrides[get_db] = override_get_db

    try:
        response = await client.get("/api/v1/home/summary")
        assert response.status_code == 200
        data = response.json()
        assert "categories" in data
        assert "Pop Culture" in data["categories"]
        assert data["active_live_games"] == 5
        # Un visiteur anonyme n'a pas de solde fictif (plus de « 3 jetons » inventés côté serveur)`n        assert data["user_balance"] == 0`n        assert data["is_authenticated"] is False
    finally:
        app.dependency_overrides.clear()
