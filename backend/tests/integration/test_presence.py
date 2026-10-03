import uuid

import fakeredis.aioredis
import pytest

from snapland.infrastructure.pubsub.redis_presence import RedisPresenceStore


@pytest.fixture
def fake_redis():
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_presence_lifecycle(fake_redis):
    store = RedisPresenceStore(fake_redis)
    u1 = uuid.uuid4()
    u2 = uuid.uuid4()
    
    # 1. Heartbeats
    await store.heartbeat(u1, "conn-1", "Alice")
    await store.heartbeat(u1, "conn-2", "Alice")
    await store.heartbeat(u2, "conn-3", "Bob")
    
    # 2. Snapshot
    snapshot = await store.snapshot()
    assert len(snapshot) == 2
    names = {u.display_name for u in snapshot}
    assert "Alice" in names
    assert "Bob" in names
    
    # 3. Remove one connection of Alice (she still has conn-2)
    is_last = await store.remove(u1, "conn-1")
    assert is_last is False
    
    # Snapshot still has Alice
    snapshot = await store.snapshot()
    assert len(snapshot) == 2
    
    # 4. Remove second connection of Alice
    is_last = await store.remove(u1, "conn-2")
    assert is_last is True
    
    # Snapshot only has Bob
    snapshot = await store.snapshot()
    assert len(snapshot) == 1
    assert snapshot[0].display_name == "Bob"


@pytest.mark.asyncio
async def test_presence_reap_expired(fake_redis):
    store = RedisPresenceStore(fake_redis)
    u1 = uuid.uuid4()
    
    # Add heartbeat with an ancient timestamp (>30s ago)
    ancient_time = 1000
    await fake_redis.zadd("presence:global", {f"{u1}:conn-old": ancient_time})
    await fake_redis.hset("presence:names", str(u1), "OldUser")
    
    expired = await store.reap_expired()
    assert len(expired) == 1
    assert expired[0] == u1
    
    # Snapshot should be empty
    snapshot = await store.snapshot()
    assert len(snapshot) == 0
