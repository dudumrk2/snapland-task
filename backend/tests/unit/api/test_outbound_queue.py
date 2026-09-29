import asyncio
import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from snapland.api.websocket.manager import Connection, WebSocketManager
from snapland.core.domain.area import Area, Coordinate
from snapland.core.domain.ws_messages import (
    AreaSavedMessage,
    AreaSavedPayload,
    CursorMoveServerMessage,
    CursorMoveServerPayload,
    RemoteDrawMessage,
    RemoteDrawPayload,
)


@pytest.fixture
def mock_ws():
    ws = MagicMock()
    ws.close = AsyncMock()
    ws.send_text = AsyncMock()
    return ws


@pytest.mark.asyncio
async def test_enqueue_normal(mock_ws):
    conn = Connection(mock_ws, uuid.uuid4(), "conn-1")
    msg = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=conn.user_id, lat=1.0, lng=2.0))
    await conn.enqueue(msg)
    assert conn.queue.qsize() == 1


@pytest.mark.asyncio
async def test_enqueue_ephemeral_overflow_drops_oldest(mock_ws):
    conn = Connection(mock_ws, uuid.uuid4(), "conn-1")
    conn.queue = asyncio.Queue(maxsize=2)
    
    msg1 = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=conn.user_id, lat=1.0, lng=1.0))
    msg2 = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=conn.user_id, lat=2.0, lng=2.0))
    msg3 = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=conn.user_id, lat=3.0, lng=3.0))
    
    await conn.enqueue(msg1)
    await conn.enqueue(msg2)
    assert conn.queue.qsize() == 2
    
    # Enqueue third -> drops msg1
    await conn.enqueue(msg3)
    assert conn.queue.qsize() == 2
    assert conn.dropped_count == 1
    
    # Dequeued item should be msg2, then msg3
    item1 = conn.queue.get_nowait()
    assert item1.payload.lat == 2.0
    item2 = conn.queue.get_nowait()
    assert item2.payload.lat == 3.0


@pytest.mark.asyncio
async def test_enqueue_durable_overflow_closes_with_1013(mock_ws):
    conn = Connection(mock_ws, uuid.uuid4(), "conn-1")
    conn.queue = asyncio.Queue(maxsize=1)
    
    ephemeral = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=conn.user_id, lat=1.0, lng=1.0))
    await conn.enqueue(ephemeral)
    
    dummy_area = Area(
        id=uuid.uuid4(), name="Area", coordinates=[], area_km2=1.0, version=1,
        created_by=conn.user_id, last_edited_by=conn.user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    durable = AreaSavedMessage(eventId="1-0", payload=AreaSavedPayload(area=dummy_area))
    
    # Enqueueing durable into full queue must close with 1013
    await conn.enqueue(durable)
    mock_ws.close.assert_called_once_with(code=1013)
    assert conn.closed is True


def test_coalesce_cursor_moves():
    manager = WebSocketManager()
    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    
    batch = [
        CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=uid1, lat=1.0, lng=1.0)),
        CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=uid2, lat=10.0, lng=10.0)),
        CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=uid1, lat=2.0, lng=2.0)),
    ]
    
    coalesced = manager._coalesce(batch)
    # Should only have 2 cursor messages (latest for uid1, and uid2)
    assert len(coalesced) == 2
    uid1_msg = next(m for m in coalesced if m.payload.userId == uid1)
    assert uid1_msg.payload.lat == 2.0


def test_coalesce_contiguous_draw_updates():
    manager = WebSocketManager()
    uid = uuid.uuid4()
    shape_id = "poly-1"
    
    batch = [
        RemoteDrawMessage(payload=RemoteDrawPayload(
            userId=uid, shapeId=shape_id, phase="update", seq=1, fromIndex=0,
            append=[Coordinate(lat=1.0, lng=1.0)]
        )),
        RemoteDrawMessage(payload=RemoteDrawPayload(
            userId=uid, shapeId=shape_id, phase="update", seq=2, fromIndex=1,
            append=[Coordinate(lat=2.0, lng=2.0)]
        )),
    ]
    
    coalesced = manager._coalesce(batch)
    assert len(coalesced) == 1
    merged = coalesced[0]
    assert merged.payload.seq == 2
    assert len(merged.payload.append) == 2
    assert merged.payload.append[0].lat == 1.0
    assert merged.payload.append[1].lat == 2.0
