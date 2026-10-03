import asyncio

from starlette.datastructures import Headers
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send
import structlog

logger = structlog.get_logger(__name__)

EXEMPT_PATHS = frozenset({"/metrics", "/health/live", "/health/ready", "/health/db"})


class TimeoutMiddleware:
    def __init__(self, app: ASGIApp, timeout_seconds: float = 30.0):
        self.app = app
        self.timeout_seconds = timeout_seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if path in EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return

        headers = Headers(scope=scope)
        if headers.get("upgrade", "").lower() == "websocket":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_wrapper(message: dict) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await asyncio.wait_for(
                self.app(scope, receive, send_wrapper),
                timeout=self.timeout_seconds,
            )
        except asyncio.TimeoutError:
            if not response_started:
                response = JSONResponse(
                    status_code=504,
                    content={
                        "error": {
                            "code": "GATEWAY_TIMEOUT",
                            "message": f"Request timed out after {int(self.timeout_seconds)} seconds",
                        }
                    },
                )
                await response(scope, receive, send)
            else:
                logger.warning(
                    "HTTP request timed out after response headers were already sent",
                    path=path,
                    timeout_seconds=self.timeout_seconds,
                )
