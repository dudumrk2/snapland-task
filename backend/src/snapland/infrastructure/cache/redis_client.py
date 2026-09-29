from redis.asyncio import Redis

from snapland.config import settings


def get_redis_client() -> Redis:
    return Redis.from_url(settings.REDIS_URL, decode_responses=True)
