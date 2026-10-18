import asyncio
import uuid
import logging
from typing import Dict
from app.core.database import AsyncSessionLocal
from app.core.websocket_manager import ws_manager
from app.services.auction_engine import AuctionEngine
from app.models.game import GameStatus

logger = logging.getLogger(__name__)


class AuctionTimerManager:
    """Autonomous countdown timer running on the server for 15s clue rounds."""

    def __init__(self):
        # session_id -> asyncio.Task
        self.running_timers: Dict[str, asyncio.Task] = {}

    def start_round_timer(
        self,
        session_id: uuid.UUID,
        duration: int,
        round_number: int,
        clue_level: int,
    ) -> None:
        """Start or restart timer for a clue round."""
        sess_str = str(session_id)
        self.cancel_timer(session_id)
        self.running_timers[sess_str] = asyncio.create_task(
            self._timer_loop(session_id, duration, round_number, clue_level)
        )

    def cancel_timer(self, session_id: uuid.UUID) -> None:
        sess_str = str(session_id)
        if sess_str in self.running_timers:
            task = self.running_timers.pop(sess_str)
            if not task.done() and task is not asyncio.current_task():
                task.cancel()

    async def _timer_loop(
        self,
        session_id: uuid.UUID,
        duration: int,
        round_number: int,
        clue_level: int,
    ) -> None:
        sess_str = str(session_id)
        try:
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

            # Timer expired: automatically advance clue or resolve round!
            async with AsyncSessionLocal() as db_session:
                result = await AuctionEngine.advance_round_clue_or_resolve(
                    session=db_session,
                    session_id=session_id,
                    expected_round=round_number,
                    expected_clue=clue_level,
                )
                await db_session.commit()

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
                # Chain next clue timer
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
            logger.exception("Error in timer loop for %s", sess_str)
        finally:
            current_task = asyncio.current_task()
            if self.running_timers.get(sess_str) == current_task:
                self.running_timers.pop(sess_str, None)

    async def resume_active_games(self) -> int:
        """Au démarrage : relance le timer des parties restées en ROUND_BIDDING (timers en mémoire perdus)."""
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
