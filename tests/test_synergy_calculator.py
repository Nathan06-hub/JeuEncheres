# -*- coding: utf-8 -*-
import pytest
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.synergy_calculator import SynergyCalculator
from app.models.game import GameSession, GameSessionPlayer
from app.models.deck import Deck, DeckItem, ItemRarity, DeckCategory
from app.models.bid import DraftedItem

@pytest.mark.asyncio
async def test_compute_game_results_empty(db_session: AsyncSession):
    fake_id = uuid.uuid4()
    result = await SynergyCalculator.compute_game_results(db_session, fake_id)
    assert result == {}

@pytest.mark.asyncio
async def test_compute_game_results_with_players(db_session: AsyncSession):
    deck = Deck(title="Test Deck", description="Un deck de test", slug="test-deck", category=DeckCategory.CINEMA)
    db_session.add(deck)
    await db_session.flush()

    game = GameSession(host_id=uuid.uuid4(), deck_id=deck.id, total_rounds=1, code="GAME01")
    db_session.add(game)
    await db_session.flush()

    player1_id = uuid.uuid4()
    p1 = GameSessionPlayer(id=player1_id, session_id=game.id, display_name="Joueur 1", remaining_budget=500, base_score_total=10)
    db_session.add(p1)
    await db_session.flush()

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

    results = await SynergyCalculator.compute_game_results(db_session, game.id)

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


@pytest.mark.asyncio
async def test_semantic_harmony_synergy_with_embeddings(db_session: AsyncSession):
    deck = Deck(title="Semantic Deck", description="Embeddings test", slug="semantic-deck", category=DeckCategory.SCIENCES)
    db_session.add(deck)
    await db_session.flush()

    game = GameSession(host_id=uuid.uuid4(), deck_id=deck.id, total_rounds=2, code="SEM001")
    db_session.add(game)
    await db_session.flush()

    p_id = uuid.uuid4()
    p = GameSessionPlayer(id=p_id, session_id=game.id, display_name="Semantic Player", remaining_budget=800, base_score_total=50)
    db_session.add(p)
    await db_session.flush()

    # Two items with high cosine similarity embeddings (identical vectors)
    vec = [0.1] * 768
    item1 = DeckItem(deck_id=deck.id, name="Item A", category="Cat A", rarity=ItemRarity.COMMON, base_score=25, clue_1="1", clue_2="2", clue_3="3", embedding=vec)
    item2 = DeckItem(deck_id=deck.id, name="Item B", category="Cat B", rarity=ItemRarity.COMMON, base_score=25, clue_1="1", clue_2="2", clue_3="3", embedding=vec)
    db_session.add_all([item1, item2])
    await db_session.flush()

    d1 = DraftedItem(session_id=game.id, round_number=1, item_id=item1.id, player_id=p.id, winning_bid_amount=100, clue_level_won=2)
    d2 = DraftedItem(session_id=game.id, round_number=2, item_id=item2.id, player_id=p.id, winning_bid_amount=100, clue_level_won=2)
    db_session.add_all([d1, d2])
    await db_session.flush()

    results = await SynergyCalculator.compute_game_results(db_session, game.id)
    comp = results["compositions"][0]
    synergy_names = [s["name"] for s in comp["synergies_breakdown"]]
    assert "Harmonie Semantique" in synergy_names
    assert comp["synergy_bonus"] == 20
