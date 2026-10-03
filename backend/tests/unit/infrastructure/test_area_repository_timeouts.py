import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy.exc import OperationalError

from snapland.infrastructure.db.repositories.area_repository import AreaRepository


@pytest.mark.asyncio
async def test_execute_with_timeout_rolls_back_on_timeout():
    mock_session = MagicMock()
    mock_session.rollback = AsyncMock()

    async def slow_execute(*args, **kwargs):
        raise asyncio.TimeoutError()

    mock_session.execute = AsyncMock(side_effect=slow_execute)

    repo = AreaRepository(mock_session)
    with pytest.raises(TimeoutError) as exc_info:
        await repo._execute_with_timeout("SELECT 1")

    assert "Database query timed out" in str(exc_info.value)
    mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_with_timeout_rolls_back_on_statement_timeout():
    mock_session = MagicMock()
    mock_session.rollback = AsyncMock()

    mock_session.execute = AsyncMock(
        side_effect=OperationalError("SELECT 1", {}, Exception("canceling statement due to statement timeout (SQLSTATE 57014)"))
    )

    repo = AreaRepository(mock_session)
    with pytest.raises(TimeoutError) as exc_info:
        await repo._execute_with_timeout("SELECT 1")

    assert "canceled by statement timeout" in str(exc_info.value)
    mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_commit_with_timeout_rolls_back_on_timeout():
    mock_session = MagicMock()
    mock_session.rollback = AsyncMock()
    mock_session.commit = AsyncMock(side_effect=asyncio.TimeoutError())

    repo = AreaRepository(mock_session)
    with pytest.raises(TimeoutError) as exc_info:
        await repo._commit_with_timeout()

    assert "Database commit timed out" in str(exc_info.value)
    mock_session.rollback.assert_awaited_once()


@pytest.mark.asyncio
async def test_execute_with_timeout_rolls_back_on_generic_db_error():
    from sqlalchemy.exc import IntegrityError

    mock_session = MagicMock()
    mock_session.rollback = AsyncMock()
    mock_session.execute = AsyncMock(side_effect=IntegrityError("INSERT ...", {}, Exception("violates foreign key")))

    repo = AreaRepository(mock_session)
    with pytest.raises(IntegrityError):
        await repo._execute_with_timeout("INSERT ...")

    mock_session.rollback.assert_awaited_once()

