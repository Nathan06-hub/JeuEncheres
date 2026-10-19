# -*- coding: utf-8 -*-
import uuid
from typing import Any, List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.core.database import get_db
from app.core.rate_limit import rate_limit
from app.core.websocket_manager import ws_manager
from app.api.deps import get_current_user, get_game_or_404, ensure_participant
from app.models.user import User
from app.models.game import GameSession, GameStatus, GameSessionPlayer
from app.models.deck import DeckItem
from app.schemas.game import GameSessionCreate, GameSessionResponse
from app.schemas.bid import BidSubmitRequest, BidResponse
from app.services.auction_engine import AuctionEngine
from app.services.timer_manager import timer_manager

router = APIRouter()


@router.post("/sessions", response_model=GameSessionResponse, summary="Créer une salle de partie")
async def create_session(
    payload: GameSessionCreate,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    names = [n.strip()[:64] for n in payload.player_names if n and n.strip()]
    if not names:
        raise HTTPException(status_code=422, detail="Au moins un nom de joueur valide est requis")
    game = await AuctionEngine.create_game_session(
        session=session,
        deck_id=payload.deck_id,
        player_names=names,
        host_user_id=current_user.id,
        starting_budget=payload.starting_budget,
        total_rounds=payload.total_rounds,
        timer_seconds=payload.timer_seconds,
        mode=payload.mode,
    )
    await session.commit()
    await session.refresh(game)
    players_res = await session.execute(
        select(GameSessionPlayer).where(GameSessionPlayer.session_id == game.id)
    )
    game.players = list(players_res.scalars().all())
    return game


@router.post("/sessions/{session_id}/start", response_model=GameSessionResponse, summary="📱 Écran 03 : Lancer la première manche de la partie")
async def start_session(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    game = await get_game_or_404(session, session_id)
    if game.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Seul l'hôte peut lancer la partie")

    game = await AuctionEngine.start_game(session=session, session_id=session_id)
    await session.commit()
    await session.refresh(game)

    await ws_manager.broadcast(str(game.id), {
        "type": "GAME_STARTED",
        "session_id": str(game.id),
        "round": game.current_round,
        "clue_level": game.current_clue_level,
        "timer_seconds": game.timer_seconds,
    })
    timer_manager.start_round_timer(
        session_id=game.id,
        duration=game.timer_seconds,
        round_number=game.current_round,
        clue_level=game.current_clue_level,
    )
    return game


@router.get("/sessions/{session_id}/live-state", summary="📱 Écran 03 : État temps réel de l'enchère (Manche, Timer, Indices et Budgets)")
async def get_live_state(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Données requises pour le Header LIVE, Timer, Carte centrale (indices secrets révélés selon niveau) et Budgets."""
    game = await get_game_or_404(session, session_id)
    await ensure_participant(session, game, current_user)

    players_res = await session.execute(
        select(GameSessionPlayer).where(GameSessionPlayer.session_id == session_id)
    )
    players = list(players_res.scalars().all())

    # Item revelation state
    item_data = None
    if game.current_item_id:
        item_res = await session.execute(select(DeckItem).where(DeckItem.id == game.current_item_id))
        item = item_res.scalar_one_or_none()
        if item:
            revealed = game.status in (GameStatus.ROUND_REVEAL, GameStatus.FINISHED)
            item_data = {
                "id": str(item.id),
                "category": item.category,
                "clue_1": item.clue_1,
                "clue_2": item.clue_2 if game.current_clue_level >= 2 else None,
                "clue_3": item.clue_3 if game.current_clue_level >= 3 else None,
                "revealed_clue_level": game.current_clue_level,
                "name_revealed": revealed,
                "name": item.name if revealed else "???",
                "base_score": item.base_score if revealed else None,
            }

    return {
        "session_id": str(game.id),
        "code": game.code,
        "status": game.status.value,
        "current_round": game.current_round,
        "total_rounds": game.total_rounds,
        "current_clue_level": game.current_clue_level,
        "timer_seconds": game.timer_seconds,
        "round_deadline": game.round_deadline,
        "item": item_data,
        "players": [
            {
                "id": str(p.id),
                "display_name": p.display_name,
                "avatar_url": p.avatar_url,
                "remaining_budget": p.remaining_budget,
                "base_score_total": p.base_score_total,
                "is_host": p.is_host,
            }
            for p in players
        ],
    }


@router.post("/sessions/{session_id}/bid", response_model=BidResponse, summary="📱 Écran 03 : Soumettre une enchère ou passer")
async def place_bid(
    session_id: uuid.UUID,
    payload: BidSubmitRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    await AuctionEngine.authorize_player(session, session_id, payload.player_id, current_user.id)

    bid = await AuctionEngine.submit_bid(
        session=session,
        session_id=session_id,
        player_id=payload.player_id,
        amount=payload.amount,
        is_pass=payload.is_pass,
    )
    await session.commit()
    await session.refresh(bid)

    await ws_manager.broadcast(str(session_id), {
        "type": "PLAYER_PASSED" if bid.is_pass else "NEW_BID",
        "session_id": str(session_id),
        "player_id": str(bid.player_id),
        "amount": bid.amount,
        "round": bid.round_number,
        "clue_level": bid.clue_level,
    })
    return bid


@router.post("/sessions/{session_id}/advance", summary="📱 Écran 03 : Dévoiler l'indice suivant (1->2->3) ou attribuer la carte")
async def advance_auction(
    session_id: uuid.UUID,
    expected_round: int,
    expected_clue: int,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    game = await get_game_or_404(session, session_id)
    if game.host_id != current_user.id:
        raise HTTPException(status_code=403, detail="Seul l'hôte peut avancer l'enchère")

    result = await AuctionEngine.advance_round_clue_or_resolve(
        session=session,
        session_id=session_id,
        expected_round=expected_round,
        expected_clue=expected_clue,
    )
    await session.commit()

    sess_str = str(session_id)
    if result["action"] == "next_clue":
        await ws_manager.broadcast(sess_str, {
            "type": "CLUE_REVEALED", "session_id": sess_str,
            "round": result["round"], "clue_level": result["clue_level"],
        })
        timer_manager.start_round_timer(session_id, game.timer_seconds, result["round"], result["clue_level"])
    else:
        await ws_manager.broadcast(sess_str, {
            "type": "ROUND_RESOLVED", "session_id": sess_str, "round": result["round"],
            "winner_player_id": result.get("winner_player_id"),
            "winner_name": result.get("winner_name"),
            "winning_amount": result.get("winning_amount"),
            "item_name": result.get("item_name"),
            "base_score": result.get("base_score"),
        })
        if result.get("game_finished"):
            timer_manager.cancel_timer(session_id)
            await ws_manager.broadcast(sess_str, {"type": "GAME_FINISHED", "session_id": sess_str})
        else:
            timer_manager.start_round_timer(session_id, game.timer_seconds, result["next_round"], 1)
    return result


async def _process_join_game(
    session: AsyncSession,
    game_id: uuid.UUID,
    current_user: User,
) -> GameSession:
    # Verrouille la ligne de la partie pour éviter la course sur la limite de 8 joueurs (F-04)
    game_res = await session.execute(
        select(GameSession).where(GameSession.id == game_id).with_for_update()
    )
    game = game_res.scalar_one_or_none()
    if not game:
        raise HTTPException(status_code=404, detail="Session d'enchères introuvable")

    if game.status in (GameStatus.FINISHED, GameStatus.CANCELLED):
        raise HTTPException(status_code=400, detail="Cette partie est déjà terminée")

    existing_player_res = await session.execute(
        select(GameSessionPlayer).where(
            GameSessionPlayer.session_id == game.id,
            GameSessionPlayer.user_id == current_user.id,
        )
    )
    existing_player = existing_player_res.scalar_one_or_none()

    if not existing_player:
        if game.status != GameStatus.LOBBY:
            raise HTTPException(status_code=400, detail="La partie a déjà commencé")

        count_res = await session.execute(
            select(func.count(GameSessionPlayer.id)).where(GameSessionPlayer.session_id == game.id)
        )
        count = count_res.scalar() or 0
        if count >= 8:
            raise HTTPException(status_code=400, detail="Ce salon est complet (max 8 joueurs)")

        new_player = GameSessionPlayer(
            session_id=game.id,
            user_id=current_user.id,
            display_name=current_user.username,
            remaining_budget=game.starting_budget,
            is_host=False,
        )
        session.add(new_player)
        await session.commit()
        await ws_manager.broadcast(str(game.id), {
            "type": "PLAYER_JOINED",
            "session_id": str(game.id),
            "player_id": str(new_player.id),
            "display_name": new_player.display_name,
            "remaining_budget": new_player.remaining_budget,
        })

    # Charger les joueurs pour la réponse
    await session.refresh(game)
    players_res = await session.execute(
        select(GameSessionPlayer).where(GameSessionPlayer.session_id == game.id)
    )
    game.players = list(players_res.scalars().all())
    return game


class JoinSessionRequest(BaseModel):
    code: str = Field(..., min_length=4, max_length=12, description="Code unique de la session")


@router.post(
    "/sessions/join",
    response_model=GameSessionResponse,
    summary="Rejoindre un salon en ligne avec un code",
    dependencies=[Depends(rate_limit("join-session", attempts=10, window=60))],
)
async def join_session_by_code(
    payload: JoinSessionRequest,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    code_clean = payload.code.strip().upper()
    game_res = await session.execute(
        select(GameSession.id).where(GameSession.code == code_clean)
    )
    game_id = game_res.scalar_one_or_none()
    if not game_id:
        raise HTTPException(status_code=404, detail="Salon introuvable avec ce code")
    return await _process_join_game(session, game_id, current_user)


@router.post("/sessions/{session_id}/join", response_model=GameSessionResponse, summary="Rejoindre un salon en ligne via son ID")
async def join_session_by_id(
    session_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    return await _process_join_game(session, session_id, current_user)


@router.post(
    "/quick-game",
    response_model=GameSessionResponse,
    summary="📱 Lancement Partie Rapide (Local / Pass & Play)",
    dependencies=[Depends(rate_limit("quick-game", attempts=5, window=60))],
)
async def launch_quick_game_alias(
    deck_id: Optional[uuid.UUID] = None,
    session: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    from app.api.v1.endpoints.home import launch_quick_game
    return await launch_quick_game(deck_id=deck_id, session=session, current_user=current_user)
