import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.synergy_calculator import SynergyCalculator
from app.models.game import GameSession, GameSessionPlayer
from app.models.deck import Deck, DeckItem, ItemRarity
from app.models.bid import DraftedItem

@pytest.mark.asyncio
async def test_compute_game_results_empty(db_session: AsyncSession):
    # Test avec une session qui n'existe pas
    fake_id = uuid.uuid4()
    result = await SynergyCalculator.compute_game_results(db_session, fake_id)
    assert result == {}

@pytest.mark.asyncio
async def test_compute_game_results_with_players(db_session: AsyncSession):
    # 1. Préparer les données en base
    deck = Deck(title="Test Deck", description="Un deck de test", slug="test-deck", category="CINEMA")
    db_session.add(deck)
    await db_session.flush()

    game = GameSession(host_id=uuid.uuid4(), deck_id=deck.id, total_rounds=1, code="GAME01")
    db_session.add(game)
    await db_session.flush()

    player1_id = uuid.uuid4()
    p1 = GameSessionPlayer(id=player1_id, session_id=game.id, display_name="Joueur 1", remaining_budget=500, base_score_total=10)
    db_session.add(p1)
    await db_session.flush()

    # Créer un item gagné (Instinct Pur = clue_level 1)
    item1 = DeckItem(deck_id=deck.id, name="Item 1", category="Science", rarity=ItemRarity.COMMON, base_score=10, clue_1="c1", clue_2="c2", clue_3="c3")
    db_session.add(item1)
    await db_session.flush()

    drafted = DraftedItem(
        session_id=game.id,
        round_number=1,
        item_id=item1.id,
        player_id=p1.id,
        winning_bid_amount=500,
        clue_level_won=1
    )
    db_session.add(drafted)
    await db_session.flush()

    # 2. Exécuter le calculateur
    results = await SynergyCalculator.compute_game_results(db_session, game.id)

    # 3. Vérifier les calculs
    assert results["session_id"] == str(game.id)
    assert len(results["podium"]) == 1
    
    podium_p1 = results["podium"][0]
    assert podium_p1["display_name"] == "Joueur 1"
    assert podium_p1["rank"] == 1
    
    assert podium_p1["final_score"] == 20

    compositions = results["compositions"]
    assert len(compositions) == 1
    comp = compositions[0]
    assert comp["synergy_bonus"] == 10

