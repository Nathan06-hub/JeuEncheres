import pytest
import uuid
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.services.auction_engine import AuctionEngine
from app.models.game import GameSession, GameSessionPlayer, GameStatus, GameMode
from app.models.deck import Deck, DeckItem, ItemRarity
from app.models.bid import Bid

@pytest.mark.asyncio
async def test_create_game_session(db_session: AsyncSession):
    deck = Deck(title="Deck", description="Desc", slug="slug", category="CINEMA")
    db_session.add(deck)
    await db_session.flush()

    host_id = uuid.uuid4()
    game = await AuctionEngine.create_game_session(
        session=db_session,
        deck_id=deck.id,
        player_names=["Alice", "Bob"],
        host_user_id=host_id,
        starting_budget=1000,
        mode=GameMode.ONLINE_MULTIPLAYER,
    )

    assert game.status == GameStatus.LOBBY
    assert game.deck_id == deck.id
    assert game.code is not None
    assert game.mode == GameMode.ONLINE_MULTIPLAYER

    players_res = await db_session.execute(select(GameSessionPlayer).where(GameSessionPlayer.session_id == game.id))
    players = list(players_res.scalars().all())
    assert len(players) == 2
    assert players[0].display_name == "Alice"
    assert players[0].is_host is True
    assert players[0].user_id == host_id

@pytest.mark.asyncio
async def test_start_game_and_submit_bid(db_session: AsyncSession):
    deck = Deck(title="Deck", description="Desc", slug="slug2", category="CINEMA")
    db_session.add(deck)
    await db_session.flush()

    item = DeckItem(deck_id=deck.id, name="Item", category="Science", rarity=ItemRarity.COMMON, base_score=10, clue_1="c1", clue_2="c2", clue_3="c3")
    db_session.add(item)
    await db_session.flush()

    game = await AuctionEngine.create_game_session(db_session, deck.id, ["Alice", "Bob"])
    
    # Start game
    started_game = await AuctionEngine.start_game(db_session, game.id)
    assert started_game.status == GameStatus.ROUND_BIDDING
    assert started_game.current_item_id == item.id
    assert started_game.current_clue_level == 1

    players_res = await db_session.execute(select(GameSessionPlayer).where(GameSessionPlayer.session_id == game.id))
    players = list(players_res.scalars().all())
    alice = next(p for p in players if p.display_name == "Alice")
    bob = next(p for p in players if p.display_name == "Bob")

    # Submit valid bid
    bid = await AuctionEngine.submit_bid(db_session, started_game.id, alice.id, 500)
    assert bid.amount == 500
    assert bid.is_pass is False
    assert bid.clue_level == 1

    # Surenchère fine minimale (+1$) : Bob enchérit 501$
    bid_fine = await AuctionEngine.submit_bid(db_session, started_game.id, bob.id, 501)
    assert bid_fine.amount == 501

    # Surenchère égale ou inférieure rejetée
    with pytest.raises(HTTPException) as exc_equal:
        await AuctionEngine.submit_bid(db_session, started_game.id, alice.id, 501)
    assert exc_equal.value.status_code == 409

    # Submit invalid bid (budget exceeded)
    with pytest.raises(HTTPException) as exc:
        await AuctionEngine.submit_bid(db_session, started_game.id, alice.id, 1500)
    assert exc.value.status_code == 400
    assert "Budget insuffisant" in exc.value.detail

@pytest.mark.asyncio
async def test_advance_round_clue_or_resolve(db_session: AsyncSession):
    deck = Deck(title="Deck3", description="Desc3", slug="slug3", category="CINEMA")
    db_session.add(deck)
    await db_session.flush()

    item = DeckItem(deck_id=deck.id, name="Item 1", category="Science", rarity=ItemRarity.COMMON, base_score=10, clue_1="c1", clue_2="c2", clue_3="c3")
    item2 = DeckItem(deck_id=deck.id, name="Item 2", category="Science", rarity=ItemRarity.COMMON, base_score=20, clue_1="c1", clue_2="c2", clue_3="c3")
    db_session.add_all([item, item2])
    await db_session.flush()

    game = await AuctionEngine.create_game_session(db_session, deck.id, ["Alice", "Bob"])
    started_game = await AuctionEngine.start_game(db_session, game.id)

    players_res = await db_session.execute(select(GameSessionPlayer).where(GameSessionPlayer.session_id == game.id))
    players = list(players_res.scalars().all())
    alice = next(p for p in players if p.display_name == "Alice")
    bob = next(p for p in players if p.display_name == "Bob")

    # Clue 1 -> Clue 2
    res = await AuctionEngine.advance_round_clue_or_resolve(db_session, started_game.id, 1, 1)
    assert res["action"] == "next_clue"
    assert res["clue_level"] == 2

    # Clue 2 -> Clue 3
    res = await AuctionEngine.advance_round_clue_or_resolve(db_session, started_game.id, 1, 2)
    assert res["action"] == "next_clue"
    assert res["clue_level"] == 3

    # Alice bids 500, Bob bids 600 on Clue 3
    await AuctionEngine.submit_bid(db_session, started_game.id, alice.id, 500)
    await AuctionEngine.submit_bid(db_session, started_game.id, bob.id, 600)

    # Resolve winner
    res = await AuctionEngine.advance_round_clue_or_resolve(db_session, started_game.id, 1, 3)
    assert res["action"] == "round_resolved"
    assert res["winner_player_id"] == str(bob.id)
    assert res["winning_amount"] == 600
