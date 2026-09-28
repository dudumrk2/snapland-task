import asyncio
from typing import AsyncIterator
from redis.asyncio import Redis
from snapland.core.interfaces.realtime import IEphemeralBus, Envelope
from pydantic import TypeAdapter

envelope_adapter = TypeAdapter(Envelope)

class RedisEphemeralBus(IEphemeralBus):
    def __init__(self, redis_client: Redis, channel: str = "snapland:ephemeral"):
        self.redis = redis_client
        self.channel = channel

    async def publish(self, envelope: Envelope) -> None:
        data = envelope_adapter.dump_json(envelope)
        await self.redis.publish(self.channel, data)

    async def subscribe(self) -> AsyncIterator[Envelope]:
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(self.channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    try:
                        envelope = envelope_adapter.validate_json(data)
                        yield envelope
                    except Exception:
                        pass
        finally:
            await pubsub.unsubscribe(self.channel)
            await pubsub.close()
