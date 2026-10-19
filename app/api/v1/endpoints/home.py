# -*- coding: utf-8 -*-
import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.api.deps import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.deck import Deck, DeckCategory, DeckItem
from app.models.game import GameSession, GameStatus, GameSessionPlayer
from app.schemas.deck import DeckSummaryResponse
from app.schemas.game import GameSessionResponse
from app.services.auction_engine import AuctionEngine
from app.services.timer_manager import timer_manager

router = APIRouter()


@router.get("", summary="Donnees completes de la page d'accueil")
@router.get("/", include_in_schema=False)
async def get_home_page(
    category: Optional[DeckCategory] = Query(None, description="Filtre par categorie"),
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Retourne l'ensemble des donnees d'accueil (resume utilisateur et decks populaires)."""
    summary = await get_home_summary(current_user=current_user, session=session)
    popular_decks = await get_popular_decks(category=category, limit=20, session=session)
    return {
        **summary,
        "popular_decks": [DeckSummaryResponse.model_validate(d).model_dump(mode="json") for d in popular_decks],
    }


@router.get("/summary", summary="📱 Ecran 01 : Donnees d'en-tete, solde jetons et compteurs")
async def get_home_summary(
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Retourne le solde de jetons (ex: ⚡ 3) et les categories disponibles."""
    active_games_res = await session.execute(
        select(func.count(GameSession.id)).where(GameSession.status == GameStatus.ROUND_BIDDING)
    )
    active_games_count = active_games_res.scalar() or 0

    return {
        "is_authenticated": current_user is not None,
        "user_balance": current_user.token_balance if current_user else 0,
        "avatar_url": current_user.avatar_url if current_user else None,
        "username": current_user.username if current_user else "Invite",
        "active_live_games": active_games_count,
        "categories": [c.value for c in DeckCategory],
    }


@router.get("/decks/popular", response_model=List[DeckSummaryResponse], summary="📱 Ecran 01 : Grille des themes populaires")
async def get_popular_decks(
    category: Optional[DeckCategory] = Query(None, description="Filtre par chip de categorie"),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Liste filtrable des themes de la communaute ou officiels classes par popularite."""
    query = select(Deck).where(Deck.is_public.is_(True))
    if category:
        query = query.where(Deck.category == category)
    query = query.order_by(Deck.play_count.desc(), Deck.likes_count.desc()).limit(limit)

    res = await session.execute(query)
    decks = res.scalars().all()
    return decks


@router.post(
    "/quick-game",
    response_model=GameSessionResponse,
    summary="📱 Ecran 01 : Lancement Partie Rapide (Local / Pass & Play)",
    dependencies=[Depends(rate_limit("quick-game", attempts=5, window=60))],
)
async def launch_quick_game(
    deck_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Cree une session rapide immediate avec 3 joueurs locaux (Joueur 1, Joueur 2, Joueur 3).

    Les joueurs 2 et 3 n'ont pas de compte : ils sont pilotes par l'hote (voir AuctionEngine.authorize_player)."""
    if not deck_id:
        popular_deck_res = await session.execute(
            select(Deck).where(Deck.is_public.is_(True)).order_by(Deck.play_count.desc()).limit(1)
        )
        deck = popular_deck_res.scalar_one_or_none()
        if not deck:
            deck = await _get_or_seed_demo_deck(session)
    else:
        deck_res = await session.execute(select(Deck).where(Deck.id == deck_id))
        deck = deck_res.scalar_one_or_none()
        if deck is None:
            raise HTTPException(status_code=404, detail="Deck introuvable")
        if not deck.is_public and deck.creator_id != current_user.id:
            raise HTTPException(status_code=403, detail="Ce deck est prive")

    player_names = [
        current_user.username,
        "Joueur 2",
        "Joueur 3",
    ]

    game = await AuctionEngine.create_game_session(
        session=session,
        deck_id=deck.id,
        player_names=player_names,
        host_user_id=current_user.id,
        starting_budget=1000,
        total_rounds=5,
    )
    # Demarrage immediat
    await AuctionEngine.start_game(session, game.id)
    await session.commit()
    await session.refresh(game)

    players_res = await session.execute(
        select(GameSessionPlayer).where(GameSessionPlayer.session_id == game.id)
    )
    game.players = list(players_res.scalars().all())

    timer_manager.start_round_timer(
        session_id=game.id,
        duration=game.timer_seconds,
        round_number=game.current_round,
        clue_level=game.current_clue_level,
    )
    return game


_DEMO_SLUG = "cinema-culte-annees-90"


async def _get_or_seed_demo_deck(session: AsyncSession) -> Deck:
    """Cree le deck de demonstration de facon idempotente."""
    existing = (await session.execute(select(Deck).where(Deck.slug == _DEMO_SLUG))).scalar_one_or_none()
    if existing:
        return existing

    deck = Deck(
        title="Cinema Culte des Annees 90",
        slug=_DEMO_SLUG,
        description="Les plus grands chefs-d'oeuvre du 7eme art des annees 90.",
        category=DeckCategory.CINEMA,
        tags=["Cinema", "Annees 90", "Culte"],
        is_official=True,
    )
    items = lambda d: [
        DeckItem(deck_id=d.id, name="Pulp Fiction", clue_1="Une montre en or et une mallette mysterieuse.", clue_2="Palme d'or 1994 signee Tarantino.", clue_3="Vincent Vega et Jules Winnfield.", base_score=95, rarity="LEGENDARY"),
        DeckItem(deck_id=d.id, name="Matrix", clue_1="Prendre la pilule rouge ou la pilule bleue.", clue_2="Revolution visuelle avec l'effet Bullet Time en 1999.", clue_3="Neo affronte l'Agent Smith.", base_score=98, rarity="LEGENDARY"),
        DeckItem(deck_id=d.id, name="Jurassic Park", clue_1="La vie trouve toujours un chemin sur une ile isolee.", clue_2="Un verre d'eau qui vibre aux pas d'un geant.", clue_3="Steven Spielberg fait revivre les dinosaures en 1993.", base_score=92, rarity="LEGENDARY"),
        DeckItem(deck_id=d.id, name="Fight Club", clue_1="La premiere regle est de ne pas en parler.", clue_2="Du savon, de l'insomnie et un narrateur anonyme.", clue_3="Tyler Durden et Edward Norton.", base_score=89, rarity="EPIC"),
        DeckItem(deck_id=d.id, name="Le Silence des Agneaux", clue_1="Un masque en cuir et du Chianti avec des feves.", clue_2="Clarice Starling enquete aupres d'un psychiatre interne.", clue_3="Anthony Hopkins incarne Hannibal Lecter.", base_score=94, rarity="LEGENDARY"),
    ]
    try:
        async with session.begin_nested():
            session.add(deck)
            await session.flush()
            session.add_all(items(deck))
            await session.flush()
    except IntegrityError:
        return (await session.execute(select(Deck).where(Deck.slug == _DEMO_SLUG))).scalar_one()
    return deck
