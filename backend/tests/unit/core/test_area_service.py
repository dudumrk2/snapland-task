import pytest
import uuid
import datetime
from unittest.mock import AsyncMock, MagicMock
from snapland.core.services.area_service import AreaService
from snapland.core.domain.area import Area, Coordinate, CreateAreaRequest, UpdateAreaRequest
from snapland.core.interfaces.services import PolygonValidation
from snapland.core.services.conflict_service import ConflictError
from snapland.core.domain.exceptions import NotFoundError

@pytest.fixture
def mock_repo():
    repo = MagicMock()
    repo.create = AsyncMock()
    repo.get_by_id = AsyncMock()
    repo.update = AsyncMock()
    repo.soft_delete = AsyncMock()
    repo.get_within_bounds = AsyncMock()
    repo.get_version_history = AsyncMock()
    return repo

@pytest.fixture
def mock_spatial():
    spatial = MagicMock()
    spatial.validate_polygon.return_value = PolygonValidation(valid=True)
    spatial.calculate_area_km2.return_value = 1.0
    return spatial

@pytest.fixture
def mock_cache():
    cache = MagicMock()
    cache.incr = AsyncMock()
    cache.get = AsyncMock()
    cache.set = AsyncMock()
    return cache

@pytest.fixture
def mock_events():
    events = MagicMock()
    events.publish = AsyncMock()
    return events

@pytest.fixture
def mock_audit():
    audit = MagicMock()
    return audit

@pytest.fixture
def area_service(mock_repo, mock_spatial, mock_cache, mock_events, mock_audit):
    return AreaService(
        repo=mock_repo,
        spatial=mock_spatial,
        cache=mock_cache,
        events=mock_events,
        audit=mock_audit
    )

@pytest.mark.asyncio
async def test_create_area_success(area_service, mock_repo, mock_cache, mock_events):
    coords = [Coordinate(lat=0.0, lng=0.0), Coordinate(lat=1.0, lng=0.0), Coordinate(lat=1.0, lng=1.0), Coordinate(lat=0.0, lng=0.0)]
    req = CreateAreaRequest(name="Test Area", coordinates=coords)
    user_id = uuid.uuid4()
    
    mock_repo.create.return_value = Area(
        id=uuid.uuid4(), name="Test Area", coordinates=coords, area_km2=1.0, version=1,
        created_by=user_id, last_edited_by=user_id, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    
    res = await area_service.create_area(req, user_id)
    
    assert res.name == "Test Area"
    mock_repo.create.assert_called_once()
    mock_cache.incr.assert_called_once_with("areas:epoch")
    mock_events.publish.assert_called_once()

@pytest.mark.asyncio
async def test_create_area_invalid_polygon(area_service, mock_spatial):
    mock_spatial.validate_polygon.return_value = PolygonValidation(valid=False, reason="SELF_INTERSECTION")
    req = CreateAreaRequest(name="Test Area", coordinates=[])
    
    with pytest.raises(ValueError, match="Invalid polygon: SELF_INTERSECTION"):
        await area_service.create_area(req, uuid.uuid4())

@pytest.mark.asyncio
async def test_update_area_success(area_service, mock_repo, mock_cache, mock_events):
    area_id = uuid.uuid4()
    user_id = uuid.uuid4()
    coords = [Coordinate(lat=0.0, lng=0.0), Coordinate(lat=1.0, lng=0.0), Coordinate(lat=1.0, lng=1.0), Coordinate(lat=0.0, lng=0.0)]
    
    current_area = Area(
        id=area_id, name="Test Area", coordinates=coords, area_km2=1.0, version=1,
        created_by=user_id, last_edited_by=user_id, created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    mock_repo.get_by_id.return_value = current_area
    mock_repo.update.return_value = Area(
        id=area_id, name="Updated Area", coordinates=coords, area_km2=1.0, version=2,
        created_by=user_id, last_edited_by=user_id, created_at=current_area.created_at, updated_at=datetime.datetime.now(datetime.UTC)
    )
    
    req = UpdateAreaRequest(version=1, name="Updated Area", coordinates=None)
    res = await area_service.update_area(area_id, req, user_id)
    
    assert res.name == "Updated Area"
    assert res.version == 2
    mock_repo.update.assert_called_once()
    mock_cache.incr.assert_called_once_with("areas:epoch")
    mock_events.publish.assert_called_once()

@pytest.mark.asyncio
async def test_update_area_conflict(area_service, mock_repo):
    area_id = uuid.uuid4()
    current_area = Area(
        id=area_id, name="Test Area", coordinates=[], area_km2=1.0, version=2,
        created_by=uuid.uuid4(), last_edited_by=uuid.uuid4(), created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    mock_repo.get_by_id.return_value = current_area
    
    req = UpdateAreaRequest(version=1, name="Updated", coordinates=None)
    
    with pytest.raises(ConflictError):
        await area_service.update_area(area_id, req, uuid.uuid4())

@pytest.mark.asyncio
async def test_delete_area(area_service, mock_repo, mock_cache, mock_events):
    area_id = uuid.uuid4()
    user_id = uuid.uuid4()
    
    await area_service.delete_area(area_id, user_id)
    
    mock_repo.soft_delete.assert_called_once_with(area_id, user_id)
    mock_cache.incr.assert_called_once_with("areas:epoch")
    mock_events.publish.assert_called_once()

@pytest.mark.asyncio
async def test_get_area_success(area_service, mock_repo):
    area_id = uuid.uuid4()
    mock_area = Area(
        id=area_id, name="Test Area", coordinates=[], area_km2=1.0, version=1,
        created_by=uuid.uuid4(), last_edited_by=uuid.uuid4(),
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    mock_repo.get_by_id.return_value = mock_area
    res = await area_service.get_area(area_id)
    assert res.id == area_id
    mock_repo.get_by_id.assert_called_once_with(area_id)

@pytest.mark.asyncio
async def test_get_area_not_found(area_service, mock_repo):
    area_id = uuid.uuid4()
    mock_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        await area_service.get_area(area_id)

@pytest.mark.asyncio
async def test_get_areas_in_bounds(area_service, mock_repo, mock_cache):
    mock_cache.get.return_value = "1" # epoch
    mock_repo.get_within_bounds.return_value = MagicMock()
    
    res = await area_service.get_areas_in_bounds(0.0, 0.0, 1.0, 1.0, zoom=10, limit=100)
    
    assert res is not None
    mock_repo.get_within_bounds.assert_called_once()

@pytest.mark.asyncio
async def test_get_history(area_service, mock_repo):
    mock_repo.get_version_history.return_value = []
    area_id = uuid.uuid4()
    
    res = await area_service.get_history(area_id)
    assert isinstance(res, list)
    mock_repo.get_version_history.assert_called_once_with(area_id)
