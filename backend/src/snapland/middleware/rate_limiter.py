import time
import uuid

from redis.asyncio import Redis
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from snapland.core.interfaces.services import IRateLimiter, RateLimitResult
from snapland.middleware.error_handler import RateLimitExceeded

LUA_SCRIPT = """
local key = KEYS[1]
local current_time = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member_id = ARGV[4]
local clear_before = current_time - window

redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, current_time, member_id)
    redis.call('EXPIRE', key, math.ceil(window / 1000))
    return {1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after = 0
    if oldest and oldest[2] then
        retry_after = math.max(0, tonumber(oldest[2]) + window - current_time)
    end
    return {0, retry_after}
end
"""

class RedisRateLimiter(IRateLimiter):
    def __init__(self, redis: Redis) -> None:
        self.redis = redis
        self._script = self.redis.register_script(LUA_SCRIPT)

    async def check_limit(self, user_id: str, bucket: str, limit: int, window_seconds: int) -> RateLimitResult:
        key = f"rate:{bucket}:{user_id}"
        current_time_ms = int(time.time() * 1000)
        window_ms = window_seconds * 1000
        member_id = f"{current_time_ms}-{uuid.uuid4()}"
        
        result = await self._script(
            keys=[key],
            args=[current_time_ms, window_ms, limit, member_id]
        )
        allowed = bool(result[0])
        retry_after_ms = int(result[1])
        
        return RateLimitResult(allowed=allowed, retry_after_ms=retry_after_ms)

async def check_rate_limit(
    limiter: IRateLimiter,
    user_id: str,
    bucket: str,
    limit: int,
    window_seconds: int
) -> None:
    result = await limiter.check_limit(user_id, bucket, limit, window_seconds)
    if not result.allowed:
        raise RateLimitExceeded(retry_after_ms=result.retry_after_ms)


class RateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        limiter = request.app.state.rate_limiter if hasattr(request.app.state, "rate_limiter") else None
        if limiter:
            forwarded = request.headers.get("X-Forwarded-For")
            ip = forwarded.split(",")[0] if forwarded else (request.client.host if request.client else "127.0.0.1")
            res = await limiter.check_limit(ip, "http", 100, 60)
            if not res.allowed:
                return JSONResponse(
                    status_code=429,
                    content={
                        "error": "RATE_LIMITED",
                        "message": "Rate limit exceeded",
                        "details": {"retryAfterMs": res.retry_after_ms}
                    },
                    headers={"Retry-After": str(max(1, res.retry_after_ms // 1000))}
                )
        return await call_next(request)
