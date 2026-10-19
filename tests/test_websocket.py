import uuid
import pytest
from app.api.v1.endpoints.auction_ws import auction_websocket
from app.core.websocket_manager import ws_manager


class _CloseCaptureWebSocket:
    def __init__(self):
        self.headers: dict[str, str] = {}
        self.closed_code: int | None = None

    async def close(self, code: int = 1000):
        self.closed_code = code


@pytest.mark.asyncio
async def test_websocket_rejects_missing_token():
    ws = _CloseCaptureWebSocket()
    await auction_websocket(ws, session_id=str(uuid.uuid4()), ticket=None, token=None)
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_token():
    ws = _CloseCaptureWebSocket()
    await auction_websocket(ws, session_id=str(uuid.uuid4()), ticket=None, token="not-a-jwt")
    assert ws.closed_code == 4401


@pytest.mark.asyncio
async def test_websocket_rejects_malformed_session_id():
    ws = _CloseCaptureWebSocket()
    await auction_websocket(ws, session_id="not-a-uuid", ticket=None, token="whatever")
    assert ws.closed_code == 4400


class _FakeWebSocket:
    def __init__(self, fail: bool = False):
        self.fail = fail
        self.accepted = False
        self.sent: list[str] = []

    async def accept(self):
        self.accepted = True

    async def send_text(self, payload: str):
        if self.fail:
            raise RuntimeError("socket closed")
        self.sent.append(payload)


@pytest.mark.asyncio
async def test_websocket_manager_broadcast_without_clients():
    # Broadcast should execute smoothly even with zero active clients
    await ws_manager.broadcast(str(uuid.uuid4()), {"type": "TEST_BROADCAST", "value": 42})


@pytest.mark.asyncio
async def test_websocket_manager_connect_broadcast_disconnect():
    session_id = str(uuid.uuid4())
    ok, dead = _FakeWebSocket(), _FakeWebSocket(fail=True)
    await ws_manager.connect(session_id, ok)
    await ws_manager.connect(session_id, dead)
    assert len(ws_manager.active_rooms[session_id]) == 2

    await ws_manager.broadcast(session_id, {"type": "PING"})
    assert len(ok.sent) == 1
    assert dead not in ws_manager.active_rooms[session_id]  # client mort purgé

    ws_manager.disconnect(session_id, ok)
    assert session_id not in ws_manager.active_rooms  # salle vide nettoyée
@pytest.mark.asyncio
async def test_websocket_manager_redis_pubsub_listener(monkeypatch):
    import asyncio
    import json
    from unittest.mock import AsyncMock, MagicMock

    session_id = str(uuid.uuid4())
    fake_socket = _FakeWebSocket()

    mock_pubsub = MagicMock()
    mock_pubsub.subscribe = AsyncMock()
    mock_pubsub.unsubscribe = AsyncMock()
    mock_pubsub.aclose = AsyncMock()

    async def _mock_listen():
        yield {'type': 'message', 'data': json.dumps({'type': 'REDIS_EVENT', 'count': 99})}

    mock_pubsub.listen = _mock_listen

    mock_redis = MagicMock()
    mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
    mock_redis.publish = AsyncMock()

    from app.core import redis
    monkeypatch.setattr(redis, 'redis_client', mock_redis)

    await ws_manager.connect(session_id, fake_socket)
    assert session_id in ws_manager.pubsub_tasks

    await asyncio.sleep(0.05)

    assert any('REDIS_EVENT' in msg for msg in fake_socket.sent)

    ws_manager.disconnect(session_id, fake_socket)
    assert session_id not in ws_manager.pubsub_tasks


@pytest.mark.asyncio
async def test_websocket_ticket_flow():
    from app.api.v1.endpoints.auction_ws import _memory_ws_tickets, _consume_ws_ticket, create_ws_ticket
    from app.models.user import User

    fake_user = User(id=uuid.uuid4(), username="ws_user", email="ws@test.com")
    ticket_resp = await create_ws_ticket(fake_user)
    assert ticket_resp.ticket.startswith("wst_")

    # Consuming valid ticket succeeds
    uid = await _consume_ws_ticket(ticket_resp.ticket)
    assert uid == fake_user.id

    # Single-use: consuming again returns None
    uid_second = await _consume_ws_ticket(ticket_resp.ticket)
    assert uid_second is None
