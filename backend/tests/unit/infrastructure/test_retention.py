from unittest.mock import AsyncMock, MagicMock

import pytest

from snapland.infrastructure.jobs.retention import (
    RETENTION_LOCK_KEY,
    RETENTION_LOCK_TTL,
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
    redis_mock.set.assert_called_once_with(RETENTION_LOCK_KEY, "instance-1", nx=True, ex=RETENTION_LOCK_TTL)
    session_factory_mock.assert_not_called()


@pytest.mark.asyncio
async def test_retention_job_executes_queries_and_retains_lock():
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.delete = AsyncMock()

    session_mock = MagicMock()
    session_mock.commit = AsyncMock()

    # Mock execute results: returns 5 rows deleted on first batch, then loop breaks since 5 < batch_size (1000)
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

    # Verify lock is retained to guard daily deduplication window
    redis_mock.delete.assert_not_called()


@pytest.mark.asyncio
async def test_retention_job_releases_lock_on_failure():
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)
    redis_mock.eval = AsyncMock()

    session_mock = MagicMock()
    session_mock.execute = AsyncMock(side_effect=RuntimeError("Database failure"))

    session_factory_mock = MagicMock()
    session_factory_mock.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    session_factory_mock.return_value.__aexit__ = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="Database failure"):
        await run_retention_job(session_factory_mock, redis_mock, "instance-1")

    # Verify lock release attempted via eval/Lua
    assert redis_mock.eval.call_count == 1
