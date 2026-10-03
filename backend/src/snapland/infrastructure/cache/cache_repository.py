from redis.asyncio import Redis

from snapland.core.interfaces.cache import ICacheRepository


class CacheRepository(ICacheRepository):
    def __init__(self, redis_client: Redis) -> None:
        self.redis = redis_client

    async def get(self, key: str) -> str | None:
        value = await self.redis.get(key)
        try:
            from snapland.middleware.metrics import cache_requests_total
            cache_requests_total.labels(layer="L2", result="hit" if value is not None else "miss").inc()
        except Exception:
            pass
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self.redis.set(key, value, ex=ttl_seconds)

    async def incr(self, key: str) -> int:
        return await self.redis.incr(key)

    async def getdel(self, key: str) -> str | None:
        value = await self.redis.getdel(key)
        try:
            from snapland.middleware.metrics import cache_requests_total
            cache_requests_total.labels(layer="L2", result="hit" if value is not None else "miss").inc()
        except Exception:
            pass
        if value is None:
            return None
        return value.decode("utf-8") if isinstance(value, bytes) else str(value)
