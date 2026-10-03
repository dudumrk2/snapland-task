import asyncio
from typing import Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.types import ASGIApp

logger = structlog.get_logger(__name__)

EXEMPT_PATHS = frozenset({"/metrics", "/health/live", "/health/ready", "/health/db"})


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: ASGIApp, timeout_seconds: float = 30.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        path = request.url.path
        if (
            path in EXEMPT_PATHS
            or path == "/ws"
            or path.startswith("/ws/")
            or request.headers.get("upgrade", "").lower() == "websocket"
        ):
            return await call_next(request)

        try:
            return await asyncio.wait_for(
                call_next(request),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            timeout_int = int(self.timeout_seconds)
            logger.warning("Request timed out", path=path, timeout_seconds=self.timeout_seconds)
            return JSONResponse(
                status_code=504,
                content={
                    "error": "TIMEOUT",
                    "message": f"Request timed out after {timeout_int}s",
                },
            )
