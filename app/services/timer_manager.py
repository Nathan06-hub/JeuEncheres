import asyncio
import json
import logging
import time
import uuid
from typing import Dict, Any, Optional

from fastapi import HTTPException
from app.core.database import AsyncSessionLocal
from app.core.websocket_manager import ws_manager
from app.services.auction_engine import AuctionEngine
from app.models.game import GameStatus

logger = logging.getLogger(__name__)


class AuctionTimerManager:
    """Gestionnaire de timers d'encheres distribue (synchronise via Redis avec repli local)."""

    def __init__(self):
        # session_id (str) -> asyncio.Task locale
        self.running_timers: Dict[str, asyncio.Task] = {}

    def start_round_timer(
        self,
        session_id: uuid.UUID,
        duration: int,
        round_number: int,
        clue_level: int,
    ) -> None:
        """Demarre ou redemarre le compte a rebours d'une manche d'indices."""
        sess_str = str(session_id)
        self.cancel_timer(session_id)
        self.running_timers[sess_str] = asyncio.create_task(
            self._timer_loop(session_id, duration, round_number, clue_level)
        )

    def cancel_timer(self, session_id: uuid.UUID) -> None:
        """Annule le decompte en local et invalide l'etat distribue dans Redis."""
        sess_str = str(session_id)
        if sess_str in self.running_timers:
            task = self.running_timers.pop(sess_str)
            if not task.done() and task is not asyncio.current_task():
                task.cancel()

        from app.core import redis as redis_module
        if redis_module.redis_client is not None:
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(redis_module.redis_client.delete(f"auction:timer:{sess_str}"))
            except RuntimeError:
                pass

    async def _sync_timer_state_to_redis(
        self,
        session_id: uuid.UUID,
        duration: int,
        round_number: int,
        clue_level: int,
    ) -> None:
        """Publie l'etat du timer et l'horodatage cible dans Redis pour les autres workers."""
        from app.core import redis as redis_module
        client = redis_module.redis_client
        if client is None:
            return
        sess_str = str(session_id)
        try:
            target_ts = time.time() + duration
            state = {
                "session_id": sess_str,
                "round": round_number,
                "clue_level": clue_level,
                "expires_at": target_ts,
                "duration": duration,
            }
            await client.set(f"auction:timer:{sess_str}", json.dumps(state), ex=duration + 60)
        except Exception as exc:
            logger.warning("Echec synchronisation Redis timer state pour %s: %s", sess_str, exc)

    async def _timer_loop(
        self,
        session_id: uuid.UUID,
        duration: int,
        round_number: int,
        clue_level: int,
    ) -> None:
        sess_str = str(session_id)
        try:
            # 1. Enregistre l'etat distribue dans Redis
            await self._sync_timer_state_to_redis(session_id, duration, round_number, clue_level)

            # 2. Boucle de tics reguliers
            for remaining in range(duration, -1, -1):
                await ws_manager.broadcast(
                    sess_str,
                    {
                        "type": "TIMER_TICK",
                        "session_id": sess_str,
                        "round": round_number,
                        "clue_level": clue_level,
                        "seconds_left": remaining,
                    },
                )
                if remaining > 0:
                    await asyncio.sleep(1)

            # 3. Synchronisation inter-processus avant declenchement de la transition
            from app.core import redis as redis_module
            client = redis_module.redis_client
            if client is not None:
                try:
                    raw_state = await client.get(f"auction:timer:{sess_str}")
                    if raw_state:
                        state = json.loads(raw_state)
                        if state.get("round") != round_number or state.get("clue_level") != clue_level:
                            logger.info(
                                "Timer pour %s ignore: manche/indice deja avance par un autre worker",
                                sess_str,
                            )
                            return

                    advance_lock_key = f"lock:advance:{sess_str}:{round_number}:{clue_level}"
                    got_lock = await client.set(advance_lock_key, "1", nx=True, ex=15)
                    if not got_lock:
                        logger.info("Transition deja prise en charge par un autre worker pour %s", sess_str)
                        return
                except Exception as exc:
                    logger.warning("Erreur verification timer distribue Redis: %s", exc)

            # 4. Expiration atteinte: resolution atomique en base
            result: Dict[str, Any] = {}
            try:
                async with AsyncSessionLocal() as db_session:
                    result = await AuctionEngine.advance_round_clue_or_resolve(
                        session=db_session,
                        session_id=session_id,
                        expected_round=round_number,
                        expected_clue=clue_level,
                    )
                    await db_session.commit()
            except HTTPException as http_exc:
                if http_exc.status_code == 409:
                    logger.info("Manche %s deja resolue pour %s (conflit normal): %s", round_number, sess_str, http_exc.detail)
                    return
                raise

            # 5. Diffusion des nouveaux evenements et enchainement
            if result.get("action") == "next_clue":
                next_level = result["clue_level"]
                await ws_manager.broadcast(
                    sess_str,
                    {
                        "type": "CLUE_REVEALED",
                        "session_id": sess_str,
                        "round": round_number,
                        "clue_level": next_level,
                    },
                )
                self.start_round_timer(
                    session_id=session_id,
                    duration=duration,
                    round_number=round_number,
                    clue_level=next_level,
                )

            elif result.get("action") == "round_resolved":
                await ws_manager.broadcast(
                    sess_str,
                    {
                        "type": "ROUND_RESOLVED",
                        "session_id": sess_str,
                        "round": round_number,
                        "winner_player_id": result.get("winner_player_id"),
                        "winner_name": result.get("winner_name"),
                        "winning_amount": result.get("winning_amount"),
                        "item_name": result.get("item_name"),
                        "base_score": result.get("base_score"),
                    },
                )

                if result.get("game_finished"):
                    await ws_manager.broadcast(sess_str, {"type": "GAME_FINISHED", "session_id": sess_str})
                else:
                    self.start_round_timer(
                        session_id=session_id,
                        duration=duration,
                        round_number=result.get("next_round", round_number + 1),
                        clue_level=1,
                    )

        except asyncio.CancelledError:
            pass
        except Exception:
            logger.exception("Erreur dans la boucle de timer pour %s", sess_str)
        finally:
            current_task = asyncio.current_task()
            if self.running_timers.get(sess_str) == current_task:
                self.running_timers.pop(sess_str, None)

    async def resume_active_games(self) -> int:
        """Au demarrage: relance le timer des parties restees en ROUND_BIDDING."""
        from datetime import datetime, timezone
        from sqlalchemy import select
        from app.models.game import GameSession

        async with AsyncSessionLocal() as db_session:
            res = await db_session.execute(
                select(GameSession).where(GameSession.status == GameStatus.ROUND_BIDDING)
            )
            games = list(res.scalars().all())

        now = datetime.now(timezone.utc)
        for game in games:
            deadline = game.round_deadline
            if deadline is not None and deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=timezone.utc)
            remaining = int((deadline - now).total_seconds()) if deadline else game.timer_seconds
            self.start_round_timer(
                session_id=game.id,
                duration=max(0, min(remaining, game.timer_seconds)),
                round_number=game.current_round,
                clue_level=game.current_clue_level,
            )
        return len(games)


timer_manager = AuctionTimerManager()
