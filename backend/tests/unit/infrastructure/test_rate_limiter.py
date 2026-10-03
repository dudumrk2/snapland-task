from unittest.mock import AsyncMock, MagicMock

import pytest

from snapland.core.interfaces.services import RateLimitResult
from snapland.middleware.error_handler import RateLimitExceeded
from snapland.middleware.rate_limiter import RedisRateLimiter, check_rate_limit


@pytest.fixture
def mock_redis():
    redis = MagicMock()
    redis.register_script = MagicMock(return_value=AsyncMock())
    return redis

@pytest.fixture
def rate_limiter(mock_redis):
    return RedisRateLimiter(redis=mock_redis)

@pytest.mark.asyncio
async def test_redis_rate_limiter_allowed(rate_limiter):
    rate_limiter._script.return_value = [1, 0]
    
    result = await rate_limiter.check_limit("user1", "auth", 5, 60)
    
    assert result.allowed is True
    assert result.retry_after_ms == 0
    rate_limiter._script.assert_called_once()

@pytest.mark.asyncio
async def test_redis_rate_limiter_denied(rate_limiter):
    rate_limiter._script.return_value = [0, 5000]
    
    result = await rate_limiter.check_limit("user1", "auth", 5, 60)
    
    assert result.allowed is False
    assert result.retry_after_ms == 5000

@pytest.mark.asyncio
async def test_check_rate_limit_allowed():
    limiter = MagicMock()
    limiter.check_limit = AsyncMock(return_value=RateLimitResult(allowed=True, retry_after_ms=0))
    
    # Should not raise
    await check_rate_limit(limiter, "user1", "auth", 5, 60)

@pytest.mark.asyncio
async def test_check_rate_limit_denied():
    limiter = MagicMock()
    limiter.check_limit = AsyncMock(return_value=RateLimitResult(allowed=False, retry_after_ms=1000))
    
    with pytest.raises(RateLimitExceeded) as exc_info:
        await check_rate_limit(limiter, "user1", "auth", 5, 60)
    
    assert exc_info.value.retry_after_ms == 1000
