import uuid
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from app.main import app
from app.core.websocket_manager import ws_manager


def _expect_close(url: str) -> int:
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(url):
            pass
    return exc.value.code


def test_websocket_rejects_missing_token():
    assert _expect_close(f"/api/v1/auction/ws/{uuid.uuid4()}") == 4401


def test_websocket_rejects_invalid_token():
    assert _expect_close(f"/api/v1/auction/ws/{uuid.uuid4()}?token=not-a-jwt") == 4401


def test_websocket_rejects_malformed_session_id():
    assert _expect_close("/api/v1/auction/ws/not-a-uuid?token=whatever") == 4400


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
