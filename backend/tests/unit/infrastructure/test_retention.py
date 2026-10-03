import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker

from snapland.infrastructure.jobs.retention import (
    RETENTION_LOCK_KEY,
    run_retention_job,
)


@pytest.mark.asyncio
async def test_retention_job_lock_contention():
    redis_mock = MagicMock()
    # Lock already held by another instance
    redis_mock.set = AsyncMock(return_value=False)
    session_factory_mock = MagicMock()

    summary = await run_retention_job(session_factory_mock, redis_mock, "instance-1")
    assert summary == {}
    redis_mock.set.assert_called_once_with(RETENTION_LOCK_KEY, "instance-1", nx=True, ex=3600)
    session_factory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_retention_job_executes_queries():
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)

    session_mock = MagicMock()
    session_mock.begin = MagicMock()
    session_mock.begin.return_value.__aenter__ = AsyncMock()
    session_mock.begin.return_value.__aexit__ = AsyncMock()

    # Mock execute results
    exec_result_mock = MagicMock()
    exec_result_mock.rowcount = 5
    session_mock.execute = AsyncMock(return_value=exec_result_mock)

    session_factory_mock = MagicMock()
    session_factory_mock.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    session_factory_mock.return_value.__aexit__ = AsyncMock()

    summary = await run_retention_job(session_factory_mock, redis_mock, "instance-1")

    assert summary["purged_soft_deleted_areas"] == 5
    assert summary["pruned_area_versions"] == 5
    assert summary["deleted_audit_logs"] == 5
    assert summary["deleted_sessions"] == 5
    assert session_mock.execute.call_count == 4
