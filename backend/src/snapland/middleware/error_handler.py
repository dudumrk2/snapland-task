import asyncio
import dataclasses
import logging
import typing

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.exc import DBAPIError

from snapland.core.domain.exceptions import (
    AuthError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    ValidationError,
)

log = logging.getLogger(__name__)

class RateLimitExceeded(Exception):
    def __init__(self, retry_after_ms: int) -> None:
        super().__init__("Rate limit exceeded")
        self.retry_after_ms = retry_after_ms

def setup_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError) -> typing.Any:
        return JSONResponse(
            status_code=400,
            content={
                "error": "VALIDATION_ERROR",
                "message": "Invalid request body",
                "details": {"reason": exc.errors()}
            }
        )

    @app.exception_handler(ValidationError)
    async def domain_validation_exception_handler(request: Request, exc: ValidationError) -> typing.Any:
        return JSONResponse(
            status_code=400,
            content={
                "error": "VALIDATION_ERROR",
                "message": str(exc) or "Validation error",
                "details": {}
            }
        )

    @app.exception_handler(AuthError)
    async def auth_error_handler(request: Request, exc: AuthError) -> typing.Any:
        return JSONResponse(
            status_code=401,
            content={
                "error": "UNAUTHORIZED",
                "message": str(exc) or "Unauthorized",
                "details": {}
            }
        )

    @app.exception_handler(ForbiddenError)
    async def forbidden_error_handler(request: Request, exc: ForbiddenError) -> typing.Any:
        return JSONResponse(
            status_code=403,
            content={
                "error": "FORBIDDEN",
                "message": str(exc) or "Forbidden",
                "details": {}
            }
        )

    @app.exception_handler(NotFoundError)
    async def not_found_error_handler(request: Request, exc: NotFoundError) -> typing.Any:
        return JSONResponse(
            status_code=404,
            content={
                "error": "NOT_FOUND",
                "message": str(exc) or "Not Found",
                "details": {}
            }
        )

    async def conflict_handler(request: Request, exc) -> typing.Any:
        area = exc.current_area
        if isinstance(area, BaseModel):
            area_dict = area.model_dump(mode="json")
        elif dataclasses.is_dataclass(area):
            area_dict = dataclasses.asdict(area) # type: ignore
        else:
            area_dict = getattr(area, "__dict__", {"value": str(area)}) # type: ignore
            
        return JSONResponse(
            status_code=409,
            content={
                "error": "CONFLICT",
                "message": "Area was modified by another user",
                "details": {
                    "current_version": getattr(area, "version", None),
                    "current_area": area_dict
                }
            }
        )

    app.add_exception_handler(ConflictError, conflict_handler)

    @app.exception_handler(RateLimitExceeded)
    async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> typing.Any:
        return JSONResponse(
            status_code=429,
            content={
                "error": "RATE_LIMITED",
                "message": "Rate limit exceeded",
                "details": {"retryAfterMs": exc.retry_after_ms}
            },
            headers={"Retry-After": str(exc.retry_after_ms // 1000)}
        )

    @app.exception_handler(TimeoutError)
    @app.exception_handler(asyncio.TimeoutError)
    async def timeout_error_handler(request: Request, exc: Exception) -> typing.Any:
        log.warning("Request timed out: %s", exc)
        return JSONResponse(
            status_code=504,
            content={
                "error": {
                    "code": "GATEWAY_TIMEOUT",
                    "message": str(exc) or "Request timed out",
                },
                "message": str(exc) or "Request timed out",
                "details": {},
            },
        )

    @app.exception_handler(DBAPIError)
    async def dbapi_error_handler(request: Request, exc: DBAPIError) -> typing.Any:
        exc_str = str(exc).lower()
        if "statement timeout" in exc_str or "canceling statement" in exc_str or "57014" in exc_str:
            log.warning("Database statement timeout: %s", exc)
            return JSONResponse(
                status_code=504,
                content={
                    "error": {
                        "code": "GATEWAY_TIMEOUT",
                        "message": "Database query timed out",
                    },
                    "message": "Database query timed out",
                    "details": {},
                },
            )
        log.exception("Unhandled database error: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Internal database error",
                "details": {},
            },
        )

    @app.exception_handler(Exception)
    async def internal_error_handler(request: Request, exc: Exception) -> typing.Any:
        log.exception("Unhandled exception: %s", exc)
        return JSONResponse(
            status_code=500,
            content={
                "error": "INTERNAL_ERROR",
                "message": "Internal server error",
                "details": {}
            }
        )
