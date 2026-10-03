from unittest.mock import AsyncMock, MagicMock

import pytest

from snapland.infrastructure.jobs.retention import (
    RETENTION_LOCK_KEY,
    RETENTION_LOCK_TTL,
    run_retention_cleanup,
    run_retention_job,
)


@pytest.mark.asyncio
async def test_retention_cleanup_alias():
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)

    session_mock = MagicMock()
    session_mock.commit = AsyncMock()
    exec_result_mock = MagicMock()
    exec_result_mock.rowcount = 2
    session_mock.execute = AsyncMock(return_value=exec_result_mock)

    session_factory_mock = MagicMock()
    session_factory_mock.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    session_factory_mock.return_value.__aexit__ = AsyncMock()

    summary = await run_retention_cleanup(session_factory_mock, redis_mock)
    assert summary["purged_soft_deleted_areas"] == 2
    assert summary["pruned_area_versions"] == 2
    assert summary["deleted_audit_logs"] == 2
    assert summary["deleted_sessions"] == 2
    redis_mock.set.assert_called_once_with(RETENTION_LOCK_KEY, "1", nx=True, ex=RETENTION_LOCK_TTL)


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

    # Verify lock release attempted via eval/Lua with exact instance_id and key
    assert redis_mock.eval.call_count == 1
    eval_call_args = redis_mock.eval.call_args[0]
    assert eval_call_args[1] == 1  # numkeys
    assert eval_call_args[2] == RETENTION_LOCK_KEY  # key
    assert eval_call_args[3] == "instance-1"  # expected owner


@pytest.mark.asyncio
async def test_retention_job_multi_batch_pagination():
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)

    session_mock = MagicMock()
    session_mock.commit = AsyncMock()

    # When batch_size=2: first query returns 2 (full batch -> loop continues), second returns 1 (incomplete -> loop breaks)
    m1 = MagicMock(rowcount=2)
    m2 = MagicMock(rowcount=1)
    # 4 tasks * 2 batches each = 8 calls
    session_mock.execute = AsyncMock(side_effect=[m1, m2, m1, m2, m1, m2, m1, m2])

    session_factory_mock = MagicMock()
    session_factory_mock.return_value.__aenter__ = AsyncMock(return_value=session_mock)
    session_factory_mock.return_value.__aexit__ = AsyncMock()

    summary = await run_retention_job(session_factory_mock, redis_mock, "instance-1", batch_size=2)
    assert summary["purged_soft_deleted_areas"] == 3
    assert summary["pruned_area_versions"] == 3
    assert summary["deleted_audit_logs"] == 3
    assert summary["deleted_sessions"] == 3
    assert session_mock.execute.call_count == 8
