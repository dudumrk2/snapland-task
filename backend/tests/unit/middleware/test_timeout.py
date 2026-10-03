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
    # Use a small timeout for test speed
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
