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
    ws.accept = AsyncMock()
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
    conn = Connection(mock_ws, uuid.uuid4(), "conn-1", maxsize=2)
    
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
async def test_enqueue_durable_evicts_ephemeral_instead_of_closing(mock_ws):
    conn = Connection(mock_ws, uuid.uuid4(), "conn-1", maxsize=1)
    
    ephemeral = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=conn.user_id, lat=1.0, lng=1.0))
    await conn.enqueue(ephemeral)
    assert conn.queue.qsize() == 1
    
    dummy_area = Area(
        id=uuid.uuid4(), name="Area", coordinates=[], area_km2=1.0, version=1,
        created_by=conn.user_id, last_edited_by=conn.user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    durable = AreaSavedMessage(eventId="1-0", payload=AreaSavedPayload(area=dummy_area))
    
    # Enqueueing durable when ephemeral is present should evict ephemeral and stay open
    await conn.enqueue(durable)
    assert conn.closed is False
    assert conn.dropped_count == 1
    assert conn.queue.qsize() == 1
    assert conn.queue.get_nowait().type == "AREA_SAVED"


@pytest.mark.asyncio
async def test_enqueue_durable_overflow_closes_with_1013_when_no_ephemeral_to_evict(mock_ws):
    conn = Connection(mock_ws, uuid.uuid4(), "conn-1", maxsize=1)
    
    dummy_area = Area(
        id=uuid.uuid4(), name="Area", coordinates=[], area_km2=1.0, version=1,
        created_by=conn.user_id, last_edited_by=conn.user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    durable1 = AreaSavedMessage(eventId="1-0", payload=AreaSavedPayload(area=dummy_area))
    durable2 = AreaSavedMessage(eventId="2-0", payload=AreaSavedPayload(area=dummy_area))
    
    await conn.enqueue(durable1)
    assert conn.queue.qsize() == 1
    
    # Enqueueing second durable into full queue of only durables closes with 1013
    await conn.enqueue(durable2)
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


def test_coalesce_different_users_same_shape_id():
    manager = WebSocketManager()
    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()
    shape_id = "shared-shape-id"

    batch = [
        RemoteDrawMessage(payload=RemoteDrawPayload(
            userId=uid1, shapeId=shape_id, phase="update", seq=1, fromIndex=0,
            append=[Coordinate(lat=1.0, lng=1.0)]
        )),
        RemoteDrawMessage(payload=RemoteDrawPayload(
            userId=uid2, shapeId=shape_id, phase="update", seq=1, fromIndex=0,
            append=[Coordinate(lat=2.0, lng=2.0)]
        )),
    ]

    coalesced = manager._coalesce(batch)
    assert len(coalesced) == 2
    assert coalesced[0].payload.userId == uid1
    assert coalesced[1].payload.userId == uid2


@pytest.mark.asyncio
async def test_disconnect_user(mock_ws):
    manager = WebSocketManager()
    uid1 = uuid.uuid4()
    uid2 = uuid.uuid4()

    conn1 = await manager.connect(mock_ws, uid1, "conn-1")
    conn2 = await manager.connect(mock_ws, uid1, "conn-2")
    conn3 = await manager.connect(mock_ws, uid2, "conn-3")

    await manager.disconnect_user(uid1)

    assert conn1.closed is True
    assert conn2.closed is True
    assert conn3.closed is False
    assert "conn-1" not in manager.active_connections
    assert "conn-2" not in manager.active_connections
    assert "conn-3" in manager.active_connections
    assert len(manager.get_user_connections(uid1)) == 0
    assert len(manager.get_user_connections(uid2)) == 1

