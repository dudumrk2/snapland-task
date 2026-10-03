import asyncio
import json
import threading
import uuid

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app
from snapland.api.websocket.manager import WebSocketManager
from snapland.infrastructure.cache.cache_repository import CacheRepository
from snapland.infrastructure.pubsub.redis_presence import RedisPresenceStore
from snapland.infrastructure.pubsub.redis_pubsub import RedisEphemeralBus
from snapland.infrastructure.pubsub.redis_streams import RedisEventStream


class ThreadSafeFakeRedisProxy:
    def __init__(self, server: fakeredis.FakeServer):
        self._server = server
        self._local = threading.local()

    def _get_redis(self):
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if not hasattr(self._local, "redis") or getattr(self._local, "loop", None) is not loop:
            self._local.loop = loop
            self._local.redis = fakeredis.aioredis.FakeRedis(server=self._server, decode_responses=True)
        return self._local.redis

    def __getattr__(self, name: str):
        return getattr(self._get_redis(), name)


@pytest.fixture
def ws_client():
    server = fakeredis.FakeServer()
    async_redis = ThreadSafeFakeRedisProxy(server)
    sync_redis = fakeredis.FakeRedis(server=server, decode_responses=True)

    from snapland.config import settings
    orig_origins = settings.WS_ALLOWED_ORIGINS
    settings.WS_ALLOWED_ORIGINS = "*"

    original_state = app.state.__dict__.copy()
    try:
        from unittest.mock import AsyncMock

        from snapland.core.interfaces.services import RateLimitResult

        mock_rate_limiter = AsyncMock()
        mock_rate_limiter.check_limit = AsyncMock(return_value=RateLimitResult(allowed=True))

        app.state.redis = async_redis
        app.state.cache_repo = CacheRepository(async_redis)
        app.state.rate_limiter = mock_rate_limiter
        app.state.presence_store = RedisPresenceStore(async_redis)
        app.state.event_stream = RedisEventStream(async_redis)
        app.state.ephemeral_bus = RedisEphemeralBus(async_redis)
        app.state.ws_manager = WebSocketManager()

        with TestClient(app) as client:
            yield client, sync_redis
    finally:
        settings.WS_ALLOWED_ORIGINS = orig_origins
        app.state.__dict__.clear()
        app.state.__dict__.update(original_state)


def test_ws_origin_rejected(ws_client):
    client, _ = ws_client
    from snapland.config import settings
    settings.WS_ALLOWED_ORIGINS = "http://trusted.com"
    try:
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect("/ws?ticket=some-ticket", headers={"origin": "http://evil.com"}):
                pass
        assert exc.value.code == 4003
    finally:
        settings.WS_ALLOWED_ORIGINS = "*"


def test_ws_invalid_ticket(ws_client):
    client, _ = ws_client
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/ws?ticket=invalid-ticket"):
            pass
    assert exc.value.code == 4001


def test_ws_valid_connection_and_presence(ws_client):
    client, sync_redis = ws_client
    user_id = str(uuid.uuid4())
    ticket = "test-ticket-123"
    
    # Store ticket in redis synchronously without binding to any loop
    sync_redis.set(f"ws_ticket:{ticket}", user_id, ex=30)
    
    with client.websocket_connect(f"/ws?ticket={ticket}") as ws:
        # Upon connecting, ticket must be deleted from redis (atomic GETDEL)
        remaining = sync_redis.get(f"ws_ticket:{ticket}")
        assert remaining is None
        
        # Receives initial batch (PRESENCE_SNAPSHOT)
        frame = ws.receive_text()
        messages = json.loads(frame)
        assert isinstance(messages, list)
        assert len(messages) >= 1
        assert messages[0]["type"] == "PRESENCE_SNAPSHOT"
        
        # Send a cursor move
        ws.send_text(json.dumps({
            "type": "CURSOR_MOVE",
            "payload": {"lat": 32.0, "lng": 34.8}
        }))


def test_ws_draw_commit_calls_area_service(ws_client):
    from unittest.mock import AsyncMock
    client, sync_redis = ws_client
    user_id = str(uuid.uuid4())
    ticket = "commit-ticket-123"

    sync_redis.set(f"ws_ticket:{ticket}", user_id, ex=30)

    mock_area_svc = AsyncMock()
    app.state.area_service = mock_area_svc

    with client.websocket_connect(f"/ws?ticket={ticket}") as ws:
        _ = ws.receive_text()  # consume initial snapshot
        ws.send_text(json.dumps({
            "type": "DRAW_COMMIT",
            "payload": {
                "shapeId": "poly-abc",
                "name": "Test Zone",
                "points": [{"lat": 32.0, "lng": 34.8}, {"lat": 32.1, "lng": 34.8}, {"lat": 32.0, "lng": 34.8}]
            }
        }))

    assert mock_area_svc.create_area.called
    call_args = mock_area_svc.create_area.call_args[0]
    assert call_args[0].name == "Test Zone"
    assert call_args[0].shape_id == "poly-abc"
    assert str(call_args[1]) == user_id


def test_ws_ticket_cannot_be_reused(ws_client):
    client, sync_redis = ws_client
    user_id = str(uuid.uuid4())
    ticket = "single-use-ticket-xyz"
    sync_redis.set(f"ws_ticket:{ticket}", user_id, ex=30)

    # First use succeeds
    with client.websocket_connect(f"/ws?ticket={ticket}") as ws:
        _ = ws.receive_text()

    # Second use fails with 4001
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect(f"/ws?ticket={ticket}"):
            pass
    assert exc.value.code == 4001


def test_ws_two_clients_collaboration(ws_client):
    client, sync_redis = ws_client
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    ticket_a = "ticket-user-a"
    ticket_b = "ticket-user-b"

    sync_redis.set(f"ws_ticket:{ticket_a}", user_a, ex=30)
    sync_redis.set(f"ws_ticket:{ticket_b}", user_b, ex=30)

    with client.websocket_connect(f"/ws?ticket={ticket_a}") as ws_a:
        # A receives initial snapshot
        frame_a = json.loads(ws_a.receive_text())
        assert frame_a[0]["type"] == "PRESENCE_SNAPSHOT"

        with client.websocket_connect(f"/ws?ticket={ticket_b}") as ws_b:
            # B receives initial snapshot
            frame_b = json.loads(ws_b.receive_text())
            assert frame_b[0]["type"] == "PRESENCE_SNAPSHOT"

            # A receives USER_JOINED for B
            frame_joined = json.loads(ws_a.receive_text())
            assert any(m["type"] == "USER_JOINED" and m["payload"]["user"]["userId"] == user_b for m in frame_joined)

            # User A moves cursor -> User B must receive CURSOR_MOVE
            ws_a.send_text(json.dumps({
                "type": "CURSOR_MOVE",
                "payload": {"lat": 32.123, "lng": 34.456}
            }))

            frame_cursor = json.loads(ws_b.receive_text())
            cursor_msg = next((m for m in frame_cursor if m["type"] == "CURSOR_MOVE"), None)
            assert cursor_msg is not None
            assert cursor_msg["payload"]["userId"] == user_a
            assert cursor_msg["payload"]["lat"] == 32.123
            assert cursor_msg["payload"]["lng"] == 34.456

            # User A sends DRAW_START -> User B must receive REMOTE_DRAW
            ws_a.send_text(json.dumps({
                "type": "DRAW_START",
                "payload": {
                    "shapeId": "poly-collab-1",
                    "append": [{"lat": 32.1, "lng": 34.4}]
                }
            }))

            frame_draw = json.loads(ws_b.receive_text())
            draw_msg = next((m for m in frame_draw if m["type"] == "REMOTE_DRAW"), None)
            assert draw_msg is not None
            assert draw_msg["payload"]["shapeId"] == "poly-collab-1"
            assert draw_msg["payload"]["phase"] == "start"


def test_ws_disconnect_triggers_user_left(ws_client):
    client, sync_redis = ws_client
    user_a = str(uuid.uuid4())
    user_b = str(uuid.uuid4())
    ticket_a = "ticket-user-left-a"
    ticket_b = "ticket-user-left-b"

    sync_redis.set(f"ws_ticket:{ticket_a}", user_a, ex=30)
    sync_redis.set(f"ws_ticket:{ticket_b}", user_b, ex=30)

    with client.websocket_connect(f"/ws?ticket={ticket_b}") as ws_b:
        _ = ws_b.receive_text()  # B's initial snapshot

        with client.websocket_connect(f"/ws?ticket={ticket_a}") as ws_a:
            _ = ws_a.receive_text()  # A's initial snapshot
            _ = ws_b.receive_text()  # B receives A's USER_JOINED
            ws_a.close()

        import time
        time.sleep(0.2)
        frame_left = json.loads(ws_b.receive_text())
        assert any(m["type"] == "USER_LEFT" and m["payload"]["userId"] == user_a for m in frame_left)


def test_ws_catchup_resync_required(ws_client):
    client, sync_redis = ws_client
    user_id = str(uuid.uuid4())
    ticket = "ticket-resync"
    sync_redis.set(f"ws_ticket:{ticket}", user_id, ex=30)

    # When lastEventId is invalid or trimmed, server must emit RESYNC_REQUIRED
    with client.websocket_connect(f"/ws?ticket={ticket}&lastEventId=invalid-stream-id") as ws:
        frame = json.loads(ws.receive_text())
        types = [m["type"] for m in frame]
        assert "RESYNC_REQUIRED" in types


def test_ws_max_connections_per_user_cap(ws_client):
    client, sync_redis = ws_client
    user_id = str(uuid.uuid4())
    connections = []

    try:
        for i in range(5):
            t = f"ticket-cap-{i}"
            sync_redis.set(f"ws_ticket:{t}", user_id, ex=30)
            ws = client.websocket_connect(f"/ws?ticket={t}")
            ws.__enter__()
            connections.append(ws)

        # 6th connection must be rejected with 4003
        t6 = "ticket-cap-overflow"
        sync_redis.set(f"ws_ticket:{t6}", user_id, ex=30)
        with pytest.raises(WebSocketDisconnect) as exc:
            with client.websocket_connect(f"/ws?ticket={t6}") as ws6:
                ws6.receive_text()
        assert exc.value.code == 4003
    finally:
        for ws in connections:
            try:
                ws.__exit__(None, None, None)
            except Exception:
                pass


def test_ws_catchup_replays_events_with_last_event_id(ws_client):
    import datetime

    from snapland.core.domain.area import Area
    from snapland.core.domain.events import AreaCreated

    client, sync_redis = ws_client
    user_id = str(uuid.uuid4())
    ticket = "ticket-replay-1"
    sync_redis.set(f"ws_ticket:{ticket}", user_id, ex=30)

    # Add an event to the stream
    stream = app.state.event_stream
    area = Area(
        id=uuid.uuid4(), name="Replay Park", coordinates=[], area_km2=1.0, version=1,
        created_by=uuid.UUID(user_id), last_edited_by=uuid.UUID(user_id),
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )

    loop = asyncio.new_event_loop()
    loop.run_until_complete(stream.publish(AreaCreated(
        area_id=area.id, created_at=area.created_at, created_by=area.created_by, area=area
    )))
    loop.close()

    with client.websocket_connect(f"/ws?ticket={ticket}&lastEventId=0-0") as ws:
        frame = json.loads(ws.receive_text())
        types = [m["type"] for m in frame]
        assert "PRESENCE_SNAPSHOT" in types
        assert "AREA_SAVED" in types

