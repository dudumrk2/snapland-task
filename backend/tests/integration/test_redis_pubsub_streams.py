import asyncio
import datetime
import uuid

import fakeredis.aioredis
import pytest

from snapland.core.domain.area import Area
from snapland.core.domain.events import AreaCreated, AreaDeleted, AreaUpdated
from snapland.core.domain.ws_messages import (
    CursorMoveServerMessage,
    CursorMoveServerPayload,
)
from snapland.core.interfaces.realtime import Envelope
from snapland.infrastructure.pubsub.redis_pubsub import RedisEphemeralBus
from snapland.infrastructure.pubsub.redis_streams import RedisEventStream


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_ephemeral_bus_publish_and_subscribe(fake_redis):
    bus = RedisEphemeralBus(fake_redis, channel="test:ephemeral")
    uid = uuid.uuid4()
    msg = CursorMoveServerMessage(payload=CursorMoveServerPayload(userId=uid, lat=32.0, lng=34.0))
    env = Envelope(origin="instance-1", message=msg)
    
    received = []
    
    async def subscriber():
        async for item in bus.subscribe():
            received.append(item)
            break
            
    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.05)
    
    await bus.publish(env)
    await asyncio.wait_for(task, timeout=2.0)
    
    assert len(received) == 1
    assert received[0].origin == "instance-1"
    assert received[0].message.type == "CURSOR_MOVE"


@pytest.mark.asyncio
async def test_event_stream_publish_and_read_since(fake_redis):
    stream = RedisEventStream(fake_redis, stream_key="test:events")
    area_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    area = Area(
        id=area_id, name="Test Park", coordinates=[], area_km2=2.5, version=1,
        created_by=user_id, last_edited_by=user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    
    # 1. Publish AreaCreated with shape_id
    created_event = AreaCreated(
        area_id=area_id, created_at=area.created_at, created_by=user_id,
        area=area, shape_id="shape-123"
    )
    await stream.publish(created_event)
    
    # Read since beginning
    catchup = await stream.read_since("0-0")
    assert catchup.resync_required is False
    assert len(catchup.events) == 1
    event_id, server_msg = catchup.events[0]
    assert server_msg.type == "AREA_SAVED"
    assert server_msg.payload.shapeId == "shape-123"
    assert server_msg.payload.area.id == area_id
    assert server_msg.eventId == event_id
    
    # 2. Publish AreaUpdated
    area.version = 2
    updated_event = AreaUpdated(
        area_id=area_id, version=2, updated_at=datetime.datetime.now(datetime.UTC),
        updated_by=user_id, area=area
    )
    await stream.publish(updated_event)
    
    catchup2 = await stream.read_since(event_id)
    assert len(catchup2.events) == 1
    assert catchup2.events[0][1].type == "AREA_UPDATED"
    assert catchup2.events[0][1].payload.area.version == 2
    
    # 3. Publish AreaDeleted
    deleted_event = AreaDeleted(
        area_id=area_id, deleted_at=datetime.datetime.now(datetime.UTC),
        deleted_by=user_id
    )
    await stream.publish(deleted_event)
    
    catchup3 = await stream.read_since(catchup2.events[0][0])
    assert len(catchup3.events) == 1
    assert catchup3.events[0][1].type == "AREA_DELETED"
    assert catchup3.events[0][1].payload.areaId == area_id


@pytest.mark.asyncio
async def test_read_since_with_bytes_key_first_entry(fake_redis):
    stream = RedisEventStream(fake_redis, stream_key="test:events_bytes")

    # Mock xinfo_stream returning bytes keys to test fallback
    original_xinfo = fake_redis.xinfo_stream

    async def mock_xinfo(_key):
        return {b"first-entry": [b"1000-0", {b"payload": b"{}"}]}

    fake_redis.xinfo_stream = mock_xinfo

    try:
        # If last_id is older than first-entry (500-0 < 1000-0), must signal resync_required=True
        catchup = await stream.read_since("500-0")
        assert catchup.resync_required is True

        # If last_id is newer than first-entry, resync_required is False
        catchup2 = await stream.read_since("1500-0")
        assert catchup2.resync_required is False
    finally:
        fake_redis.xinfo_stream = original_xinfo

