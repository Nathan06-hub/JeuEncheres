import asyncio
import json
import logging
from typing import Dict, Set, Any
from fastapi import WebSocket

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 2.0


class ConnectionManager:
    """Manages live WebSockets for auction rooms with Redis Pub/Sub support."""

    def __init__(self):
        # session_id -> Set of active WebSocket connections
        self.active_rooms: Dict[str, Set[WebSocket]] = {}
        # session_id -> Redis PubSub listener task
        self.pubsub_tasks: Dict[str, asyncio.Task] = {}

    async def connect(self, session_id: str, websocket: WebSocket, subprotocol: str | None = None) -> None:
        """Accept and register WebSocket connection in room."""
        if subprotocol is not None:
            await websocket.accept(subprotocol=subprotocol)
        else:
            await websocket.accept()
        if session_id not in self.active_rooms:
            self.active_rooms[session_id] = set()
            self._start_redis_listener(session_id)
        self.active_rooms[session_id].add(websocket)
        logger.info("WebSocket client connected to room %s. Total: %d", session_id, len(self.active_rooms[session_id]))

    def disconnect(self, session_id: str, websocket: WebSocket) -> None:
        """Remove disconnected socket."""
        if session_id in self.active_rooms:
            self.active_rooms[session_id].discard(websocket)
            if not self.active_rooms[session_id]:
                del self.active_rooms[session_id]
                self._stop_redis_listener(session_id)
        logger.info("WebSocket client disconnected from room %s", session_id)

    def _start_redis_listener(self, session_id: str) -> None:
        """Lance une tâche asynchrone d'écoute Pub/Sub dédiée au canal auction:{session_id}."""
        from app.core.redis import redis_client
        if redis_client is None:
            return
        existing_task = self.pubsub_tasks.get(session_id)
        if existing_task is not None and not existing_task.done():
            return

        async def _listen():
            pubsub = redis_client.pubsub()
            channel = f"auction:{session_id}"
            try:
                await pubsub.subscribe(channel)
                async for message in pubsub.listen():
                    if message and message.get("type") == "message":
                        data = message.get("data")
                        payload = data.decode("utf-8") if isinstance(data, bytes) else str(data)
                        await self._broadcast_local(session_id, payload)
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                logger.warning("Erreur pubsub listener pour %s: %s", channel, exc)
            finally:
                try:
                    await pubsub.unsubscribe(channel)
                    await pubsub.aclose()
                except Exception:
                    pass

        task = asyncio.create_task(_listen())
        task.add_done_callback(lambda _: self.pubsub_tasks.pop(session_id, None))
        self.pubsub_tasks[session_id] = task

    def _stop_redis_listener(self, session_id: str) -> None:
        """Annule et nettoie la tâche de souscription Redis lorsque la salle devient vide."""
        task = self.pubsub_tasks.pop(session_id, None)
        if task and not task.done():
            task.cancel()

    async def broadcast(self, session_id: str, message: Dict[str, Any]) -> None:
        """Broadcast message to all connected clients in a session."""
        payload = json.dumps(message)

        # 1. Publish to Redis if available for multi-instance sync
        from app.core.redis import redis_client
        published = False
        if redis_client is not None:
            try:
                await redis_client.publish(f"auction:{session_id}", payload)
                published = True
            except Exception as exc:
                logger.warning("Redis publish failed: %s", exc)

        # 2. Si Redis n'est pas actif ou si la tâche d'écoute locale n'est pas active sur cette salle,
        #    diffuser immédiatement en local.
        listener_task = self.pubsub_tasks.get(session_id)
        has_active_listener = listener_task is not None and not listener_task.done()
        if not published or not has_active_listener:
            await self._broadcast_local(session_id, payload)

    async def _broadcast_local(self, session_id: str, payload: str) -> None:
        if session_id not in self.active_rooms:
            return

        connections = list(self.active_rooms[session_id])

        async def _send(conn: WebSocket) -> bool:
            try:
                # Un client lent ne doit pas bloquer toute la salle
                await asyncio.wait_for(conn.send_text(payload), timeout=SEND_TIMEOUT_SECONDS)
                return True
            except Exception as exc:
                logger.debug("WebSocket send failed in room %s: %s", session_id, exc)
                return False

        results = await asyncio.gather(*(_send(c) for c in connections))

        room = self.active_rooms.get(session_id)
        if room is None:
            return
        for conn, ok in zip(connections, results):
            if not ok:
                room.discard(conn)
        if not room:
            self.active_rooms.pop(session_id, None)
            self._stop_redis_listener(session_id)


ws_manager = ConnectionManager()
