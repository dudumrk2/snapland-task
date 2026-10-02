import json
from typing import AsyncIterator

from pydantic import TypeAdapter
from redis.asyncio import Redis

from snapland.core.interfaces.realtime import Envelope, IEphemeralBus

envelope_adapter = TypeAdapter(Envelope)

CONTROL_CHANNEL = "snapland:control"


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
            if hasattr(pubsub, "aclose"):
                await pubsub.aclose()
            else:
                await pubsub.close()

    async def publish_control(self, cmd: dict) -> None:
        """Publish a control command (e.g. logout) to every instance."""
        await self.redis.publish(CONTROL_CHANNEL, json.dumps(cmd))

    async def subscribe_control(self) -> AsyncIterator[dict]:
        """Yield control commands sent from any instance (including self)."""
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(CONTROL_CHANNEL)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = message["data"]
                    try:
                        yield json.loads(data)
                    except Exception:
                        pass
        finally:
            await pubsub.unsubscribe(CONTROL_CHANNEL)
            if hasattr(pubsub, "aclose"):
                await pubsub.aclose()
            else:
                await pubsub.close()
