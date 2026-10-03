import asyncio

import pytest
from fastapi import FastAPI

from main import supervise


@pytest.mark.asyncio
async def test_supervise_marks_healthy_after_delay():
    app = FastAPI()
    app.state.bg_tasks_status = {"test_worker": False}

    async def healthy_worker(_app):
        # Long-running healthy loop
        while True:
            await asyncio.sleep(0.1)

    task = asyncio.create_task(supervise("test_worker", app, healthy_worker))

    # Initially False
    assert app.state.bg_tasks_status["test_worker"] is False

    # Wait for the 1.0s health timer
    await asyncio.sleep(1.2)
    assert app.state.bg_tasks_status["test_worker"] is True

    # Clean cancellation
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


@pytest.mark.asyncio
async def test_supervise_marks_unhealthy_on_crash():
    app = FastAPI()
    app.state.bg_tasks_status = {"crashing_worker": False}
    attempts = 0

    async def crashing_worker(_app):
        nonlocal attempts
        attempts += 1
        await asyncio.sleep(0.1)
        raise RuntimeError("boom")

    task = asyncio.create_task(supervise("crashing_worker", app, crashing_worker))

    await asyncio.sleep(0.3)
    # Crashed before 1.0s => remains False
    assert app.state.bg_tasks_status["crashing_worker"] is False
    assert attempts >= 1

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
