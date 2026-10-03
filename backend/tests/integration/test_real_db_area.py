import datetime
import uuid

import pytest

from snapland.core.domain.area import Area, Coordinate
from snapland.core.domain.user import User
from snapland.infrastructure.db.repositories.area_repository import AreaRepository
from snapland.infrastructure.db.repositories.user_repository import UserRepository


@pytest.mark.asyncio
async def test_real_db_area_lifecycle(db_session):
    user_repo = UserRepository(db_session)
    area_repo = AreaRepository(db_session)

    # 1. Create a user
    user_id = uuid.uuid4()
    test_user = User(
        id=user_id,
        email=f"test_{user_id.hex[:8]}@example.com",
        display_name="Real DB Tester",
        password_hash="hashed_pw"
    )
    await user_repo.create(test_user)

    # 2. Create Area in PostGIS
    area_id = uuid.uuid4()
    coords = [
        Coordinate(lat=32.0, lng=34.0),
        Coordinate(lat=32.0, lng=35.0),
        Coordinate(lat=33.0, lng=35.0),
        Coordinate(lat=32.0, lng=34.0)
    ]
    area = Area(
        id=area_id,
        name="Real PostGIS Polygon",
        coordinates=coords,
        area_km2=0.0,
        version=1,
        created_by=user_id,
        last_edited_by=user_id,
        created_at=datetime.datetime.now(datetime.timezone.utc),
        updated_at=datetime.datetime.now(datetime.timezone.utc)
    )

    created = await area_repo.create(area)
    assert created.id == area_id
    assert created.area_km2 > 0.0

    # 3. Fetch Area by ID (verifying GET /areas/{id} repository path)
    fetched = await area_repo.get_by_id(area_id)
    assert fetched is not None
    assert fetched.id == area_id
    assert fetched.name == "Real PostGIS Polygon"
    assert len(fetched.coordinates) >= 3

    # 4. Fetch Area within bounds (verifying ST_Intersects / GiST index)
    page = await area_repo.get_within_bounds(33.5, 31.5, 35.5, 33.5, zoom=10, limit=50)
    found = [a for a in page.areas if a.id == area_id]
    assert len(found) == 1

    # 5. Update Area with OCC
    fetched.name = "Real PostGIS Polygon Updated"
    updated = await area_repo.update(fetched, expected_version=1)
    assert updated is not None
    assert updated.version == 2
    assert updated.name == "Real PostGIS Polygon Updated"

    # 6. Verify version history
    history = await area_repo.get_version_history(area_id)
    assert len(history) >= 2
    version_numbers = [v.version_number for v in history]
    assert 1 in version_numbers
    assert 2 in version_numbers

    # 7. Soft delete
    deleted = await area_repo.soft_delete(area_id, user_id)
    assert deleted is True

    # 8. Verify get_by_id returns None after soft delete
    fetched_after_delete = await area_repo.get_by_id(area_id)
    assert fetched_after_delete is None
