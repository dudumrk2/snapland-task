import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from snapland.api.websocket.handlers import dispatch_message
from snapland.api.websocket.manager import Connection
from snapland.core.interfaces.services import RateLimitResult


@pytest.fixture
def mock_conn():
    ws = MagicMock()
    ws.close = AsyncMock()
    ws.send_text = AsyncMock()
    conn = Connection(ws, uuid.uuid4(), "conn-test")
    conn.enqueue = AsyncMock()
    return conn


@pytest.fixture
def mock_app_state():
    import datetime

    from snapland.core.domain.area import Area
    
    state = MagicMock()
    state.rate_limiter = MagicMock()
    state.rate_limiter.check_limit = AsyncMock(return_value=RateLimitResult(allowed=True))
    state.ephemeral_bus = MagicMock()
    state.ephemeral_bus.publish = AsyncMock()
    state.event_stream = MagicMock()
    state.event_stream.publish = AsyncMock()
    state.area_service = MagicMock()
    
    mock_area = Area(
        id=uuid.uuid4(),
        name="Mock",
        coordinates=[],
        area_km2=1.0,
        version=1,
        created_by=uuid.uuid4(),
        last_edited_by=uuid.uuid4(),
        created_at=datetime.datetime.now(),
        updated_at=datetime.datetime.now()
    )
    state.area_service.create_area = AsyncMock(return_value=mock_area)
    state.ws_manager = MagicMock()
    state.ws_manager.broadcast_ephemeral = AsyncMock()
    return state


@pytest.mark.asyncio
async def test_dispatch_invalid_json(mock_conn, mock_app_state):
    await dispatch_message(mock_conn, "not-valid-json", mock_app_state)
    mock_conn.enqueue.assert_called_once()
    msg = mock_conn.enqueue.call_args[0][0]
    assert msg.type == "ERROR"
    assert msg.payload.code == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_dispatch_rate_limited_draw_start(mock_conn, mock_app_state):
    mock_app_state.rate_limiter.check_limit.return_value = RateLimitResult(allowed=False, retry_after_ms=5000)
    raw = '{"type":"DRAW_START","payload":{"shapeId":"s1","point":{"lat":32.0,"lng":34.0}}}'
    await dispatch_message(mock_conn, raw, mock_app_state)
    
    mock_conn.enqueue.assert_called_once()
    msg = mock_conn.enqueue.call_args[0][0]
    assert msg.type == "ERROR"
    assert msg.payload.code == "RATE_LIMITED"
    assert msg.payload.retryAfterMs == 5000


@pytest.mark.asyncio
async def test_dispatch_cursor_move_publishes_envelope(mock_conn, mock_app_state):
    raw = '{"type":"CURSOR_MOVE","payload":{"lat":32.1,"lng":34.8}}'
    await dispatch_message(mock_conn, raw, mock_app_state)
    
    mock_app_state.ephemeral_bus.publish.assert_called_once()
    env = mock_app_state.ephemeral_bus.publish.call_args[0][0]
    assert env.message.type == "CURSOR_MOVE"
    assert env.message.payload.userId == mock_conn.user_id
    assert env.message.payload.lat == 32.1


@pytest.mark.asyncio
async def test_dispatch_cursor_move_sent_at_pass_through_and_clamping(mock_conn, mock_app_state):
    import time
    now_epoch = time.time()

    # Valid sentAt
    raw_valid = f'{{"type":"CURSOR_MOVE","payload":{{"lat":32.1,"lng":34.8,"sentAt":{now_epoch}}}}}'
    await dispatch_message(mock_conn, raw_valid, mock_app_state)
    env = mock_app_state.ephemeral_bus.publish.call_args[0][0]
    assert env.message.payload.sentAt == pytest.approx(now_epoch, abs=0.01)

    # Bogus future timestamp (> now + 5s) - must be discarded
    mock_conn.last_cursor_time = 0.0  # reset throttle
    raw_future = f'{{"type":"CURSOR_MOVE","payload":{{"lat":32.1,"lng":34.8,"sentAt":{now_epoch + 1000.0}}}}}'
    await dispatch_message(mock_conn, raw_future, mock_app_state)
    env2 = mock_app_state.ephemeral_bus.publish.call_args[0][0]
    assert env2.message.payload.sentAt is None


@pytest.mark.asyncio
async def test_dispatch_draw_commit_calls_create_area_with_shape_id(mock_conn, mock_app_state):
    raw = '{"type":"DRAW_COMMIT","payload":{"shapeId":"shape-abc","name":"My Park","points":[{"lat":32.0,"lng":34.0},{"lat":32.1,"lng":34.0},{"lat":32.1,"lng":34.1},{"lat":32.0,"lng":34.0}]}}'
    await dispatch_message(mock_conn, raw, mock_app_state)
    
    # 1. Publishes ephemeral REMOTE_DRAW(commit)
    mock_app_state.ephemeral_bus.publish.assert_called_once()
    env = mock_app_state.ephemeral_bus.publish.call_args[0][0]
    assert env.message.type == "REMOTE_DRAW"
    assert env.message.payload.phase == "commit"
    assert env.message.payload.shapeId == "shape-abc"
    
    # 2. Calls area_service.create_area with shape_id in request
    mock_app_state.area_service.create_area.assert_called_once()
    req, uid = mock_app_state.area_service.create_area.call_args[0]
    assert req.name == "My Park"
    assert req.shape_id == "shape-abc"
    assert uid == mock_conn.user_id


@pytest.mark.asyncio
async def test_dispatch_ping_replies_with_pong(mock_conn, mock_app_state):
    raw = '{"type":"PING"}'
    await dispatch_message(mock_conn, raw, mock_app_state)
    mock_conn.enqueue.assert_called_once()
    msg = mock_conn.enqueue.call_args[0][0]
    assert msg.type == "PONG"


@pytest.mark.asyncio
async def test_dispatch_pong_updates_keepalive_timestamps(mock_conn, mock_app_state):
    mock_conn.last_ping_time = 123.0
    raw = '{"type":"PONG"}'
    await dispatch_message(mock_conn, raw, mock_app_state)
    assert mock_conn.last_ping_time is None
    assert mock_conn.last_pong_time > 0
