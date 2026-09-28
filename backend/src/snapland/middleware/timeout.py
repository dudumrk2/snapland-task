import asyncio
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
import structlog
from fastapi.responses import JSONResponse

logger = structlog.get_logger(__name__)

class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout: float = 30.0):
        super().__init__(app)
        self.timeout = timeout

    async def dispatch(self, request: Request, call_next):
        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout)
        except asyncio.TimeoutError:
            logger.error("Request timeout", route=request.url.path, method=request.method)
            return JSONResponse({"detail": "Gateway Timeout"}, status_code=504)
