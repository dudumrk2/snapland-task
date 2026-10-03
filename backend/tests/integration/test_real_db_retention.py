import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from snapland.infrastructure.db.models import AreaModel, SessionModel, UserModel
from snapland.infrastructure.jobs.retention import run_retention_job


@pytest.mark.asyncio
async def test_real_db_retention_job_lifecycle(db_session):
    now = datetime.now(timezone.utc)
    user_id = uuid.uuid4()

    # 1. Setup test user
    user = UserModel(
        id=user_id,
        email=f"retention_{user_id.hex[:8]}@snapland.test",
        password_hash="pw_hash",
        display_name="Retention Tester",
        created_at=now,
        updated_at=now,
    )
    db_session.add(user)
    await db_session.flush()

    # 2. Add an old soft-deleted area (> 90 days)
    old_deleted_area_id = uuid.uuid4()
    old_deleted_area = AreaModel(
        id=old_deleted_area_id,
        name="Old Deleted Area",
        geom="SRID=4326;POLYGON((34.0 32.0, 34.0 32.1, 34.1 32.1, 34.1 32.0, 34.0 32.0))",
        area_km2=10.0,
        version=1,
        created_by=user_id,
        last_edited_by=user_id,
        created_at=now - timedelta(days=120),
        updated_at=now - timedelta(days=100),
        deleted_at=now - timedelta(days=95),
    )

    # 3. Add an active area
    active_area_id = uuid.uuid4()
    active_area = AreaModel(
        id=active_area_id,
        name="Active Area",
        geom="SRID=4326;POLYGON((34.0 32.0, 34.0 32.1, 34.1 32.1, 34.1 32.0, 34.0 32.0))",
        area_km2=10.0,
        version=1,
        created_by=user_id,
        last_edited_by=user_id,
        created_at=now,
        updated_at=now,
        deleted_at=None,
    )

    # 4. Add an old expired session (> 30 days)
    old_session_id = uuid.uuid4()
    old_session = SessionModel(
        id=old_session_id,
        user_id=user_id,
        family_id=uuid.uuid4(),
        refresh_token_hash="hash_old",
        expires_at=now - timedelta(days=35),
        revoked_at=None,
        ip_address="127.0.0.1",
        created_at=now - timedelta(days=40),
    )

    db_session.add_all([old_deleted_area, active_area, old_session])
    await db_session.commit()

    # 5. Run retention job with session maker bound to current engine
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    redis_mock = MagicMock()
    redis_mock.set = AsyncMock(return_value=True)

    summary = await run_retention_job(session_factory, redis_mock, "test-instance")

    assert summary["purged_soft_deleted_areas"] >= 1
    assert summary["deleted_sessions"] >= 1

    # 6. Verify database state
    r1 = await db_session.execute(select(AreaModel).where(AreaModel.id == old_deleted_area_id))
    assert r1.scalar_one_or_none() is None

    r2 = await db_session.execute(select(AreaModel).where(AreaModel.id == active_area_id))
    assert r2.scalar_one_or_none() is not None

    r3 = await db_session.execute(select(SessionModel).where(SessionModel.id == old_session_id))
    assert r3.scalar_one_or_none() is None
