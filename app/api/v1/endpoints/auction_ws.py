import asyncio
import json
import uuid
import logging
import jwt
import time
from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, HTTPException, WebSocket, WebSocketDisconnect, Query, Depends
from app.api.deps import get_current_user
from app.models.user import User
from sqlalchemy import select
from app.core.websocket_manager import ws_manager
from app.core.database import AsyncSessionLocal
from app.core.config import settings
from app.models.game import GameSession, GameSessionPlayer, GameStatus
from app.services.auction_engine import AuctionEngine
from app.services.timer_manager import timer_manager

logger = logging.getLogger(__name__)

router = APIRouter()

MAX_MESSAGE_BYTES = 2048
IDLE_TIMEOUT_SECONDS = 60
MAX_MESSAGES_PER_SECOND = 10
WS_TICKET_TTL_SECONDS = 60

_memory_ws_tickets: dict[str, tuple[uuid.UUID, float]] = {}


class WsTicketResponse(BaseModel):
    ticket: str
    expires_in: int = WS_TICKET_TTL_SECONDS


@router.post(
    "/ws-ticket",
    response_model=WsTicketResponse,
    summary="Generer un ticket a usage unique pour connexion WebSocket (evite d exposer le JWT en URL)",
)
async def create_ws_ticket(current_user: User = Depends(get_current_user)) -> WsTicketResponse:
    ticket = f"wst_{uuid.uuid4().hex}"
    from app.core import redis as redis_module
    client = redis_module.redis_client
    if client is not None:
        try:
            await client.set(f"ws_ticket:{ticket}", str(current_user.id), ex=WS_TICKET_TTL_SECONDS)
            return WsTicketResponse(ticket=ticket)
        except Exception as exc:
            logger.warning("Erreur stockage ticket Redis: %s", exc)

    _memory_ws_tickets[ticket] = (current_user.id, time.monotonic() + WS_TICKET_TTL_SECONDS)
    return WsTicketResponse(ticket=ticket)


async def _consume_ws_ticket(ticket: str) -> Optional[uuid.UUID]:
    if not ticket:
        return None
    from app.core import redis as redis_module
    client = redis_module.redis_client
    if client is not None:
        try:
            lua_getdel = """
            local val = redis.call('get', KEYS[1])
            if val then
                redis.call('del', KEYS[1])
            end
            return val
            """
            val = await client.eval(lua_getdel, 1, f"ws_ticket:{ticket}")
            if val:
                return uuid.UUID(str(val))
        except Exception as exc:
            logger.warning("Erreur validation ticket Redis: %s", exc)

    if ticket in _memory_ws_tickets:
        uid, expires_at = _memory_ws_tickets.pop(ticket)
        if time.monotonic() <= expires_at:
            return uid
    return None


def _error_payload(exc: Exception) -> dict:
    """Message d'erreur sûr : le détail n'est exposé que pour les erreurs métier (HTTPException)."""
    if isinstance(exc, HTTPException):
        return {"type": "ERROR", "code": exc.status_code, "message": str(exc.detail)}
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return {"type": "ERROR", "code": 422, "message": "Message invalide"}
    logger.exception("Erreur WebSocket inattendue", exc_info=exc)
    return {"type": "ERROR", "code": 500, "message": "Erreur interne"}


async def _snapshot(session_uuid: uuid.UUID) -> dict | None:
    """État courant de la partie, envoyé à la (re)connexion pour resynchroniser le client."""
    async with AsyncSessionLocal() as session:
        game = (await session.execute(select(GameSession).where(GameSession.id == session_uuid))).scalar_one_or_none()
        if not game:
            return None
        return {
            "type": "STATE_SNAPSHOT",
            "session_id": str(game.id),
            "status": game.status.value,
            "round": game.current_round,
            "total_rounds": game.total_rounds,
            "clue_level": game.current_clue_level,
            "round_deadline": game.round_deadline.isoformat() if game.round_deadline else None,
        }


@router.websocket("/ws/{session_id}")
async def auction_websocket(
    websocket: WebSocket,
    session_id: str,
    token: Optional[str] = Query(None),
    ticket: Optional[str] = Query(None),
):
    """📱 Écran 03 : WebSocket temps réel pour timer, révélation d'indices et enchères en direct."""
    try:
        session_uuid = uuid.UUID(session_id)
        session_id = str(session_uuid)  # clé de salle canonique (minuscules), partagée avec les broadcasts HTTP
    except ValueError:
        await websocket.close(code=4400)
        return

    # Extraction depuis subprotocol si fourni
    subprotocols = websocket.headers.get("sec-websocket-protocol", "")
    for proto in [p.strip() for p in subprotocols.split(",") if p.strip()]:
        if proto.startswith("ticket."):
            ticket = proto.split("ticket.", 1)[1]
            break
        elif proto.startswith("bearer."):
            token = proto.split("bearer.", 1)[1]
            break

    user_uuid: Optional[uuid.UUID] = None
    if ticket:
        user_uuid = await _consume_ws_ticket(ticket)
        if user_uuid is None:
            await websocket.close(code=4401)
            return
    elif token:
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
            user_uuid = uuid.UUID(str(payload.get("sub")))
        except (jwt.PyJWTError, ValueError, TypeError):
            await websocket.close(code=4401)
            return
    else:
        await websocket.close(code=4401)
        return

    async with AsyncSessionLocal() as session:
        game = (await session.execute(select(GameSession).where(GameSession.id == session_uuid))).scalar_one_or_none()
        if not game:
            await websocket.close(code=4404)
            return
        own_player = (await session.execute(
            select(GameSessionPlayer).where(
                GameSessionPlayer.session_id == session_uuid,
                GameSessionPlayer.user_id == user_uuid,
            )
        )).scalars().first()
        is_host = game.host_id == user_uuid
        if own_player is None and not is_host:
            await websocket.close(code=4403)
            return
        own_player_id = own_player.id if own_player else None

    await ws_manager.connect(session_id, websocket)

    try:
        await websocket.send_json({
            "type": "CONNECTED",
            "session_id": session_id,
            "player_id": str(own_player_id) if own_player_id else None,
            "is_host": is_host,
            "message": "Connecté à la salle d'enchères en direct",
        })
        snapshot = await _snapshot(session_uuid)
        if snapshot:
            await websocket.send_json(snapshot)

        window_start = asyncio.get_running_loop().time()
        window_count = 0

        while True:
            try:
                raw_data = await asyncio.wait_for(websocket.receive_text(), timeout=IDLE_TIMEOUT_SECONDS)
            except asyncio.TimeoutError:
                await websocket.close(code=4408)  # inactivité : le client doit se reconnecter
                break

            now = asyncio.get_running_loop().time()
            if now - window_start >= 1:
                window_start, window_count = now, 0
            window_count += 1
            if window_count > MAX_MESSAGES_PER_SECOND:
                await websocket.send_json({"type": "ERROR", "code": 429, "message": "Trop de messages"})
                continue

            if len(raw_data) > MAX_MESSAGE_BYTES:
                await websocket.send_json({"type": "ERROR", "code": 413, "message": "Message trop volumineux"})
                continue

            try:
                data = json.loads(raw_data)
                if not isinstance(data, dict):
                    raise ValueError("objet JSON attendu")
            except (json.JSONDecodeError, ValueError):
                await websocket.send_json({"type": "ERROR", "code": 400, "message": "Format JSON invalide"})
                continue

            action = data.get("action")

            if action == "ping":
                await websocket.send_json({"type": "pong"})
                continue

            if action == "sync":
                snap = await _snapshot(session_uuid)
                if snap:
                    await websocket.send_json(snap)
                continue

            try:
                if action == "start_game":
                    if not is_host:
                        raise HTTPException(status_code=403, detail="Seul l'hôte peut lancer la partie")

                    async with AsyncSessionLocal() as session:
                        current = (await session.execute(
                            select(GameSession).where(GameSession.id == session_uuid)
                        )).scalar_one()
                        if current.status == GameStatus.LOBBY:
                            game = await AuctionEngine.start_game(session=session, session_id=session_uuid)
                            await session.commit()
                        elif current.status == GameStatus.ROUND_BIDDING:
                            game = current  # déjà démarrée (ex. via /quick-game) : on (re)lance seulement le timer
                        else:
                            raise HTTPException(status_code=409, detail="La partie est terminée ou annulée")

                    await ws_manager.broadcast(session_id, {
                        "type": "GAME_STARTED",
                        "session_id": session_id,
                        "round": game.current_round,
                        "clue_level": game.current_clue_level,
                        "timer_seconds": game.timer_seconds,
                    })
                    if session_id not in timer_manager.running_timers:
                        timer_manager.start_round_timer(
                            session_id=game.id,
                            duration=game.timer_seconds,
                            round_number=game.current_round,
                            clue_level=game.current_clue_level,
                        )

                elif action in ("bid", "pass"):
                    raw_player = data.get("player_id")
                    player_uuid = uuid.UUID(str(raw_player)) if raw_player else own_player_id
                    if player_uuid is None:
                        raise HTTPException(status_code=422, detail="player_id requis")
                    is_pass = action == "pass"
                    amount = 0
                    if not is_pass:
                        amount = data.get("amount")
                        if isinstance(amount, bool) or not isinstance(amount, int):
                            raise HTTPException(status_code=422, detail="Montant invalide")

                    async with AsyncSessionLocal() as session:
                        # L'identité vient du JWT : jamais du seul player_id fourni par le client
                        await AuctionEngine.authorize_player(session, session_uuid, player_uuid, user_uuid)
                        bid = await AuctionEngine.submit_bid(
                            session=session,
                            session_id=session_uuid,
                            player_id=player_uuid,
                            amount=amount,
                            is_pass=is_pass,
                        )
                        await session.commit()

                    await ws_manager.broadcast(session_id, {
                        "type": "PLAYER_PASSED" if is_pass else "NEW_BID",
                        "session_id": session_id,
                        "player_id": str(player_uuid),
                        "amount": bid.amount,
                        "round": bid.round_number,
                        "clue_level": bid.clue_level,
                    })
                else:
                    raise HTTPException(status_code=400, detail="Action inconnue")
            except Exception as e:
                await websocket.send_json(_error_payload(e))

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error(f"WebSocket fatal error in {session_id}: {exc}")
    finally:
        ws_manager.disconnect(session_id, websocket)
