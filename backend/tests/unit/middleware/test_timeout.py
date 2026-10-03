import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from snapland.middleware.timeout import TimeoutMiddleware


def test_timeout_middleware_fast_request():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=1.0)

    @app.get("/fast")
    async def fast_handler():
        return {"status": "ok"}

    client = TestClient(app)
    resp = client.get("/fast")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_timeout_middleware_slow_request_returns_504():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=0.05)

    @app.get("/slow")
    async def slow_handler():
        await asyncio.sleep(0.2)
        return {"status": "too_late"}

    client = TestClient(app)
    resp = client.get("/slow")
    assert resp.status_code == 504
    data = resp.json()
    assert data["error"]["code"] == "GATEWAY_TIMEOUT"


def test_timeout_middleware_exempt_paths():
    app = FastAPI()
    app.add_middleware(TimeoutMiddleware, timeout_seconds=0.05)

    @app.get("/metrics")
    async def metrics_handler():
        await asyncio.sleep(0.1)
        return "metrics_content"

    @app.get("/health/live")
    async def health_handler():
        await asyncio.sleep(0.1)
        return {"status": "ok"}

    client = TestClient(app)
    resp1 = client.get("/metrics")
    assert resp1.status_code == 200

    resp2 = client.get("/health/live")
    assert resp2.status_code == 200


def test_error_handler_timeout_error_returns_504():
    from snapland.middleware.error_handler import setup_error_handlers

    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/db-timeout")
    async def db_timeout_handler():
        raise TimeoutError("Database query timed out after 28.0s")

    client = TestClient(app)
    resp = client.get("/db-timeout")
    assert resp.status_code == 504
    data = resp.json()
    assert data["error"]["code"] == "GATEWAY_TIMEOUT"
    assert "timed out" in data["error"]["message"]


def test_error_handler_db_statement_timeout_returns_504():
    from snapland.middleware.error_handler import setup_error_handlers
    from sqlalchemy.exc import OperationalError

    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/statement-timeout")
    async def statement_timeout_handler():
        raise OperationalError("SELECT 1", {}, Exception("canceling statement due to statement timeout (SQLSTATE 57014)"))

    client = TestClient(app)
    resp = client.get("/statement-timeout")
    assert resp.status_code == 504
    data = resp.json()
    assert data["error"]["code"] == "GATEWAY_TIMEOUT"
    assert "Database query timed out" in data["error"]["message"]

