import asyncio
from typing import Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


class TimeoutMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, timeout_seconds: float = 30.0):
        super().__init__(app)
        self.timeout_seconds = timeout_seconds

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Skip websocket upgrades and internal health / metrics
        if request.scope.get("type") == "websocket" or request.headers.get("upgrade", "").lower() == "websocket":
            return await call_next(request)

        try:
            return await asyncio.wait_for(call_next(request), timeout=self.timeout_seconds)
        except asyncio.TimeoutError:
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "GATEWAY_TIMEOUT",
                        "message": f"Request timed out after {int(self.timeout_seconds)} seconds",
                    }
                },
            )
