import datetime
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

from main import app
from snapland.api.deps import get_area_service, get_auth_service, get_rate_limiter
from snapland.api.v1.auth import get_current_user_id
from snapland.core.domain.area import Area
from snapland.core.interfaces.repositories import AreaPage
from snapland.core.interfaces.services import RateLimitResult

client = TestClient(app)

def mock_get_current_user_id():
    return uuid.UUID("11111111-1111-1111-1111-111111111111")

def mock_get_rate_limiter():
    limiter = MagicMock()
    limiter.check_limit = AsyncMock(return_value=RateLimitResult(allowed=True, retry_after_ms=0))
    return limiter

@pytest.fixture
def auth_service_mock():
    return MagicMock()

@pytest.fixture
def area_service_mock():
    svc = MagicMock()
    svc.get_areas_in_bounds = AsyncMock()
    svc.create_area = AsyncMock()
    svc.get_area = AsyncMock()
    svc.update_area = AsyncMock()
    svc.delete_area = AsyncMock()
    svc.get_history = AsyncMock()
    return svc

@pytest.fixture(autouse=True)
def override_dependencies(area_service_mock, auth_service_mock):
    app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
    app.dependency_overrides[get_rate_limiter] = mock_get_rate_limiter
    app.dependency_overrides[get_area_service] = lambda: area_service_mock
    app.dependency_overrides[get_auth_service] = lambda: auth_service_mock
    yield
    app.dependency_overrides = {}

def test_get_areas(area_service_mock):
    area_service_mock.get_areas_in_bounds.return_value = AreaPage(areas=[], truncated=False)
    
    response = client.get("/api/v1/areas?bounds=34.0,31.0,35.0,32.0&zoom=10&limit=50")
    
    assert response.status_code == 200
    assert response.json() == {"areas": [], "truncated": False}
    area_service_mock.get_areas_in_bounds.assert_called_once_with(34.0, 31.0, 35.0, 32.0, zoom=10, limit=50)

def test_get_areas_unauthorized(area_service_mock):
    # Temporarily remove auth override to test unauthenticated rejection
    del app.dependency_overrides[get_current_user_id]
    try:
        response = client.get("/api/v1/areas?bounds=34.0,31.0,35.0,32.0&zoom=10&limit=50")
        assert response.status_code == 401
    finally:
        app.dependency_overrides[get_current_user_id] = mock_get_current_user_id

def test_create_area(area_service_mock):
    area_id = uuid.uuid4()
    user_id = mock_get_current_user_id()
    
    area_service_mock.create_area.return_value = Area(
        id=area_id, name="Test Area", coordinates=[], area_km2=1.0, version=1,
        created_by=user_id, last_edited_by=user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    
    payload = {
        "name": "Test Area",
        "coordinates": [{"lat": 0.0, "lng": 0.0}, {"lat": 1.0, "lng": 0.0}, {"lat": 1.0, "lng": 1.0}, {"lat": 0.0, "lng": 0.0}]
    }
    
    response = client.post("/api/v1/areas", json=payload)
    
    assert response.status_code == 200
    assert response.json()["name"] == "Test Area"
    area_service_mock.create_area.assert_called_once()

def test_update_area(area_service_mock):
    area_id = uuid.uuid4()
    user_id = mock_get_current_user_id()
    
    area_service_mock.update_area.return_value = Area(
        id=area_id, name="Updated", coordinates=[], area_km2=1.0, version=2,
        created_by=user_id, last_edited_by=user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    
    payload = {
        "version": 1,
        "name": "Updated"
    }
    
    response = client.put(f"/api/v1/areas/{area_id}", json=payload)
    
    assert response.status_code == 200
    assert response.json()["name"] == "Updated"
    assert response.json()["version"] == 2
    area_service_mock.update_area.assert_called_once()

def test_delete_area(area_service_mock):
    area_id = uuid.uuid4()
    
    response = client.delete(f"/api/v1/areas/{area_id}")
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    area_service_mock.delete_area.assert_called_once_with(area_id, mock_get_current_user_id())

def test_get_history(area_service_mock):
    area_id = uuid.uuid4()
    area_service_mock.get_history.return_value = []
    
    response = client.get(f"/api/v1/areas/{area_id}/history")
    
    assert response.status_code == 200
    assert response.json() == []
    area_service_mock.get_history.assert_called_once_with(area_id)

def test_get_area(area_service_mock):
    area_id = uuid.uuid4()
    user_id = mock_get_current_user_id()
    area_service_mock.get_area.return_value = Area(
        id=area_id, name="Test Area", coordinates=[], area_km2=1.0, version=1,
        created_by=user_id, last_edited_by=user_id,
        created_at=datetime.datetime.now(datetime.UTC), updated_at=datetime.datetime.now(datetime.UTC)
    )
    
    response = client.get(f"/api/v1/areas/{area_id}")
    
    assert response.status_code == 200
    assert response.json()["id"] == str(area_id)
    area_service_mock.get_area.assert_called_once_with(area_id)

def test_get_area_not_found(area_service_mock):
    from snapland.core.domain.exceptions import NotFoundError
    area_id = uuid.uuid4()
    area_service_mock.get_area.side_effect = NotFoundError("Area not found")
    
    response = client.get(f"/api/v1/areas/{area_id}")
    
    assert response.status_code == 404
