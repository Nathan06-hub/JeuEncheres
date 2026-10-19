import random
import secrets
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.game import GameSession, GameSessionPlayer, GameStatus, GameMode
from app.models.deck import Deck, DeckItem
from app.models.bid import Bid, DraftedItem

_ROOM_CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
_ROOM_CODE_LENGTH = 8


def _generate_room_code() -> str:
    return "".join(secrets.choice(_ROOM_CODE_ALPHABET) for _ in range(_ROOM_CODE_LENGTH))


class AuctionEngine:
    """Real-time auction logic for blind clues, timer management and drafting attribution."""

    @staticmethod
    async def _ordered_item_ids(session: AsyncSession, game: GameSession) -> List[uuid.UUID]:
        """Ordre des cartes de la partie : mélange déterministe (graine = id de la partie).

        Évite que toutes les parties révèlent les cartes dans le même ordre (score décroissant)
        tout en restant reproductible entre le démarrage et chaque manche suivante.
        """
        res = await session.execute(
            select(DeckItem.id)
            .where(DeckItem.deck_id == game.deck_id)
            .order_by(DeckItem.base_score.desc(), DeckItem.id.asc())
        )
        ids = list(res.scalars().all())
        random.Random(game.id.int).shuffle(ids)
        return ids

    @staticmethod
    async def authorize_player(
        session: AsyncSession,
        session_id: uuid.UUID,
        player_id: uuid.UUID,
        user_id: uuid.UUID,
    ) -> GameSessionPlayer:
        """Retourne le joueur si `user_id` a le droit d'agir pour lui, sinon 403.

        Droit d'agir : le joueur est lié à ce compte, OU c'est un joueur local sans compte
        (Pass & Play) d'une partie dont `user_id` est l'hôte.
        """
        player = (await session.execute(
            select(GameSessionPlayer).where(
                GameSessionPlayer.id == player_id,
                GameSessionPlayer.session_id == session_id,
            )
        )).scalar_one_or_none()
        if player is None:
            raise HTTPException(status_code=403, detail="Action non autorisée pour ce joueur")
        if player.user_id == user_id:
            return player
        if player.user_id is None:
            host_id = (await session.execute(
                select(GameSession.host_id).where(GameSession.id == session_id)
            )).scalar_one_or_none()
            if host_id is not None and host_id == user_id:
                return player
        raise HTTPException(status_code=403, detail="Action non autorisée pour ce joueur")

    @staticmethod
    async def create_game_session(
        session: AsyncSession,
        deck_id: uuid.UUID,
        player_names: List[str],
        host_user_id: Optional[uuid.UUID] = None,
        starting_budget: int = 1000,
        total_rounds: int = 10,
        timer_seconds: int = 15,
        mode: GameMode = GameMode.LOCAL_PASS_AND_PLAY,
    ) -> GameSession:
        """Initialize a new GameSession with players and room code."""
        # Verify deck exists and caller has access (M-03)
        deck_res = await session.execute(select(Deck).where(Deck.id == deck_id))
        deck = deck_res.scalar_one_or_none()
        if not deck:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deck introuvable")
        if not deck.is_public and (host_user_id is None or deck.creator_id != host_user_id):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Ce deck est privé")

        # Plafond de parties actives par hôte (E-02)
        if host_user_id is not None:
            active_count_res = await session.execute(
                select(func.count(GameSession.id)).where(
                    GameSession.host_id == host_user_id,
                    GameSession.status == GameStatus.ROUND_BIDDING,
                )
            )
            active_count = active_count_res.scalar() or 0
            if active_count >= settings.MAX_ACTIVE_GAMES_PER_HOST:
                raise HTTPException(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    detail=f"Nombre maximal de parties actives atteint ({settings.MAX_ACTIVE_GAMES_PER_HOST})",
                )

        # Génération de code de salle 8 caractères base32 avec retry sur collision (F-05)
        game: Optional[GameSession] = None
        for _ in range(5):
            candidate_code = _generate_room_code()
            candidate = GameSession(
                code=candidate_code,
                host_id=host_user_id,
                deck_id=deck_id,
                mode=mode,
                starting_budget=starting_budget,
                total_rounds=total_rounds,
                current_round=1,
                current_clue_level=1,
                timer_seconds=timer_seconds,
                status=GameStatus.LOBBY,
            )
            try:
                async with session.begin_nested():
                    session.add(candidate)
                    await session.flush()
                game = candidate
                break
            except IntegrityError:
                continue

        if game is None:
            raise HTTPException(status_code=500, detail="Impossible de générer un code de salle unique")

        # Add players
        for idx, name in enumerate(player_names):
            p = GameSessionPlayer(
                session_id=game.id,
                user_id=host_user_id if (idx == 0 and host_user_id) else None,
                display_name=name,
                remaining_budget=starting_budget,
                is_host=(idx == 0),
            )
            session.add(p)

        await session.flush()
        return game

    @staticmethod
    async def start_game(session: AsyncSession, session_id: uuid.UUID) -> GameSession:
        """Start game session and select first auction item (uniquement depuis le LOBBY)."""
        game_res = await session.execute(
            select(GameSession).where(GameSession.id == session_id).with_for_update()
        )
        game = game_res.scalar_one_or_none()
        if not game:
            raise HTTPException(status_code=404, detail="Partie introuvable")
        if game.status != GameStatus.LOBBY:
            raise HTTPException(status_code=409, detail="La partie a déjà démarré ou est terminée")

        item_ids = await AuctionEngine._ordered_item_ids(session, game)
        if not item_ids:
            raise HTTPException(status_code=400, detail="Le deck ne contient aucun item")

        # Jamais plus de manches que de cartes : sinon la même carte serait réattribuée.
        game.total_rounds = min(game.total_rounds, len(item_ids))
        game.status = GameStatus.ROUND_BIDDING
        game.current_round = 1
        game.current_clue_level = 1
        game.current_item_id = item_ids[0]
        game.started_at = datetime.now(timezone.utc)
        game.round_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.timer_seconds)

        await session.flush()
        return game

    @staticmethod
    async def submit_bid(
        session: AsyncSession,
        session_id: uuid.UUID,
        player_id: uuid.UUID,
        amount: int,
        is_pass: bool = False,
    ) -> Bid:
        """Submit a bid for the active round item."""
        # Lock session & player
        game_res = await session.execute(
            select(GameSession).where(GameSession.id == session_id).with_for_update()
        )
        game = game_res.scalar_one_or_none()
        if not game or game.status != GameStatus.ROUND_BIDDING:
            raise HTTPException(status_code=400, detail="La manche d'enchères n'est pas active")

        now = datetime.now(timezone.utc)
        deadline = game.round_deadline
        if deadline is not None:
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            if now > deadline:
                raise HTTPException(status_code=400, detail="Le temps de la manche est écoulé")

        player_res = await session.execute(
            select(GameSessionPlayer).where(GameSessionPlayer.id == player_id).with_for_update()
        )
        player = player_res.scalar_one_or_none()
        if not player or player.session_id != session_id:
            raise HTTPException(status_code=404, detail="Joueur non inscrit dans cette partie")

        already_passed = (await session.execute(
            select(Bid.id).where(
                Bid.session_id == session_id,
                Bid.player_id == player_id,
                Bid.round_number == game.current_round,
                Bid.is_pass.is_(True),
            ).limit(1)
        )).first()
        if already_passed:
            raise HTTPException(status_code=409, detail="Vous avez déjà passé cette manche")

        if not is_pass:
            if amount <= 0:
                raise HTTPException(status_code=400, detail="Le montant de l'enchère doit être positif")
            if amount > player.remaining_budget:
                raise HTTPException(
                    status_code=400,
                    detail=f"Budget insuffisant (Requis: {amount}, Dispo: {player.remaining_budget})",
                )
            top = (await session.execute(
                select(func.max(Bid.amount)).where(
                    Bid.session_id == session_id,
                    Bid.round_number == game.current_round,
                    Bid.is_pass.is_(False),
                )
            )).scalar() or 0
            if amount <= top:
                raise HTTPException(
                    status_code=409,
                    detail=f"Surenchère minimale : l'offre doit dépasser {top}",
                )

        bid = Bid(
            session_id=session_id,
            player_id=player_id,
            item_id=game.current_item_id,
            round_number=game.current_round,
            clue_level=game.current_clue_level,
            amount=0 if is_pass else amount,
            is_pass=is_pass,
        )
        session.add(bid)
        await session.flush()
        return bid

    @staticmethod
    async def advance_round_clue_or_resolve(
        session: AsyncSession,
        session_id: uuid.UUID,
        expected_round: int,
        expected_clue: int,
    ) -> Dict[str, Any]:
        """Advance to next clue level (1 -> 2 -> 3) or resolve winner if clue 3 finished."""
        game_res = await session.execute(
            select(GameSession).where(GameSession.id == session_id).with_for_update()
        )
        game = game_res.scalar_one_or_none()
        if not game:
            raise HTTPException(status_code=404, detail="Partie introuvable")

        if game.status != GameStatus.ROUND_BIDDING:
            raise HTTPException(status_code=400, detail="L'état du jeu n'est pas actif pour une enchère")

        if game.current_round != expected_round or game.current_clue_level != expected_clue:
            raise HTTPException(status_code=409, detail="Désynchronisation: la manche ou l'indice ne correspond pas")

        if game.current_clue_level < 3:
            # Advance clue level
            game.current_clue_level += 1
            game.round_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.timer_seconds)
            await session.flush()
            return {
                "action": "next_clue",
                "round": game.current_round,
                "clue_level": game.current_clue_level,
            }

        # Resolve winner of the current round
        bids_res = await session.execute(
            select(Bid)
            .where(
                Bid.session_id == session_id,
                Bid.round_number == game.current_round,
                Bid.is_pass.is_(False),
            )
            .order_by(Bid.amount.desc(), Bid.clue_level.asc(), Bid.created_at.asc())
        )
        winning_bid = bids_res.scalars().first()

        item_res = await session.execute(select(DeckItem).where(DeckItem.id == game.current_item_id))
        won_item = item_res.scalar_one_or_none()

        result = {
            "action": "round_resolved",
            "round": game.current_round,
            "winner_player_id": None,
            "winning_amount": 0,
            "item_name": won_item.name if won_item else "",
            "base_score": won_item.base_score if won_item else 0,
        }

        if winning_bid and won_item:
            winning_bid.is_winning_bid = True
            winner_player_res = await session.execute(
                select(GameSessionPlayer)
                .where(GameSessionPlayer.id == winning_bid.player_id)
                .with_for_update()
            )
            winner = winner_player_res.scalar_one()
            winner.remaining_budget = max(0, winner.remaining_budget - winning_bid.amount)
            winner.base_score_total += won_item.base_score
            winner.final_score = winner.base_score_total + winner.synergy_bonus

            # Record drafted item
            drafted = DraftedItem(
                session_id=session_id,
                player_id=winner.id,
                item_id=won_item.id,
                winning_bid_amount=winning_bid.amount,
                clue_level_won=winning_bid.clue_level,
                round_number=game.current_round,
            )
            session.add(drafted)

            result["winner_player_id"] = str(winner.id)
            result["winning_amount"] = winning_bid.amount
            result["winner_name"] = winner.display_name

        # Check if game finished or advance to next round
        game_finished = False
        item_ids: List[uuid.UUID] = []
        if game.current_round < game.total_rounds:
            item_ids = await AuctionEngine._ordered_item_ids(session, game)

        if game.current_round >= game.total_rounds or game.current_round >= len(item_ids):
            game.status = GameStatus.FINISHED
            game.ended_at = datetime.now(timezone.utc)
            game_finished = True
        else:
            game.current_round += 1
            game.current_clue_level = 1
            game.current_item_id = item_ids[game.current_round - 1]
            game.round_deadline = datetime.now(timezone.utc) + timedelta(seconds=game.timer_seconds)

        result["game_finished"] = game_finished
        result["next_round"] = game.current_round

        await session.flush()
        return result
