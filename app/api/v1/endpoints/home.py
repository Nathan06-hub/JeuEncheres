import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.api.deps import get_current_user, get_current_user_optional
from app.models.user import User
from app.models.deck import Deck, DeckCategory, DeckItem
from app.models.game import GameSession, GameStatus
from app.schemas.deck import DeckSummaryResponse
from app.schemas.game import GameSessionResponse
from app.services.auction_engine import AuctionEngine
from app.services.timer_manager import timer_manager

router = APIRouter()


@router.get("/summary", summary="📱 Écran 01 : Données d'en-tête, solde jetons et compteurs")
async def get_home_summary(
    current_user: Optional[User] = Depends(get_current_user_optional),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Retourne le solde de jetons (ex: ⚡ 3) et les catégories disponibles."""
    active_games_res = await session.execute(
        select(func.count(GameSession.id)).where(GameSession.status == GameStatus.ROUND_BIDDING)
    )
    active_games_count = active_games_res.scalar() or 0

    return {
        "is_authenticated": current_user is not None,
        "user_balance": current_user.token_balance if current_user else 0,
        "avatar_url": current_user.avatar_url if current_user else None,
        "username": current_user.username if current_user else "Invité",
        "active_live_games": active_games_count,
        "categories": [c.value for c in DeckCategory],
    }


@router.get("/decks/popular", response_model=List[DeckSummaryResponse], summary="📱 Écran 01 : Grille des thèmes populaires")
async def get_popular_decks(
    category: Optional[DeckCategory] = Query(None, description="Filtre par chip de catégorie"),
    limit: int = Query(20, ge=1, le=50),
    session: AsyncSession = Depends(get_db),
) -> Any:
    """Liste filtrable des thèmes de la communauté ou officiels classés par popularité."""
    query = select(Deck).where(Deck.is_public.is_(True))
    if category:
        query = query.where(Deck.category == category)
    query = query.order_by(Deck.play_count.desc(), Deck.likes_count.desc()).limit(limit)

    res = await session.execute(query)
    decks = res.scalars().all()
    return decks


@router.post("/quick-game", response_model=GameSessionResponse, summary="📱 Écran 01 : Lancement Partie Rapide (Local / Pass & Play)")
async def launch_quick_game(
    deck_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Crée une session rapide immédiate avec 3 joueurs locaux (Joueur 1, Joueur 2, Joueur 3).

    Les joueurs 2 et 3 n'ont pas de compte : ils sont pilotés par l'hôte (voir AuctionEngine.authorize_player)."""
    if not deck_id:
        # Pick the most popular public deck
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
            raise HTTPException(status_code=403, detail="Ce deck est privé")

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
    # Start immediately
    await AuctionEngine.start_game(session, game.id)
    await session.commit()
    await session.refresh(game)

    timer_manager.start_round_timer(
        session_id=game.id,
        duration=game.timer_seconds,
        round_number=game.current_round,
        clue_level=game.current_clue_level,
    )
    return game


_DEMO_SLUG = "cinema-culte-annees-90"


async def _get_or_seed_demo_deck(session: AsyncSession) -> Deck:
    """Crée le deck de démonstration de façon idempotente (slug unique : sûr en cas d'appels concurrents)."""
    existing = (await session.execute(select(Deck).where(Deck.slug == _DEMO_SLUG))).scalar_one_or_none()
    if existing:
        return existing

    deck = Deck(
        title="Cinéma Culte des Années 90",
        slug=_DEMO_SLUG,
        description="Les plus grands chefs-d'œuvre du 7ème art des années 90.",
        category=DeckCategory.CINEMA,
        tags=["Cinéma", "Années 90", "Culte"],
        is_official=True,
    )
    items = lambda d: [
        DeckItem(deck_id=d.id, name="Pulp Fiction", clue_1="Une montre en or et une mallette mystérieuse.", clue_2="Palme d'or 1994 signée Tarantino.", clue_3="Vincent Vega et Jules Winnfield.", base_score=95, rarity="LEGENDARY"),
        DeckItem(deck_id=d.id, name="Matrix", clue_1="Prendre la pilule rouge ou la pilule bleue.", clue_2="Révolution visuelle avec l'effet Bullet Time en 1999.", clue_3="Néo affronte l'Agent Smith.", base_score=98, rarity="LEGENDARY"),
        DeckItem(deck_id=d.id, name="Jurassic Park", clue_1="La vie trouve toujours un chemin sur une île isolée.", clue_2="Un verre d'eau qui vibre aux pas d'un géant.", clue_3="Steven Spielberg fait revivre les dinosaures en 1993.", base_score=92, rarity="LEGENDARY"),
        DeckItem(deck_id=d.id, name="Fight Club", clue_1="La première règle est de ne pas en parler.", clue_2="Du savon, de l'insomnie et un narrateur anonyme.", clue_3="Tyler Durden et Edward Norton.", base_score=89, rarity="EPIC"),
        DeckItem(deck_id=d.id, name="Le Silence des Agneaux", clue_1="Un masque en cuir et du Chianti avec des fèves.", clue_2="Clarice Starling enquête auprès d'un psychiatre interné.", clue_3="Anthony Hopkins incarne Hannibal Lecter.", base_score=94, rarity="LEGENDARY"),
    ]
    try:
        async with session.begin_nested():
            session.add(deck)
            await session.flush()
            session.add_all(items(deck))
            await session.flush()
    except IntegrityError:
        # Un autre appel concurrent a créé le deck entre-temps
        return (await session.execute(select(Deck).where(Deck.slug == _DEMO_SLUG))).scalar_one()
    return deck
