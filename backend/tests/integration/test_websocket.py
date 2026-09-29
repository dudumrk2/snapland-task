import json
import uuid

import fakeredis.aioredis
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from main import app
from snapland.api.websocket.route import manager as ws_manager
from snapland.infrastructure.cache.cache_repository import CacheRepository
from snapland.infrastructure.pubsub.redis_presence import RedisPresenceStore
from snapland.infrastructure.pubsub.redis_pubsub import RedisEphemeralBus
from snapland.infrastructure.pubsub.redis_streams import RedisEventStream


@pytest.fixture
def ws_client():
    server = fakeredis.FakeServer()
    async_redis = fakeredis.aioredis.FakeRedis(server=server, decode_responses=True)
    sync_redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    
    app.state.redis = async_redis
    app.state.cache_repo = CacheRepository(async_redis)
    app.state.presence_store = RedisPresenceStore(async_redis)
    app.state.event_stream = RedisEventStream(async_redis)
    app.state.ephemeral_bus = RedisEphemeralBus(async_redis)
    app.state.ws_manager = ws_manager
    
    with TestClient(app) as client:
        yield client, sync_redis


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
