import pytest
import uuid
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock
from main import app
from snapland.api.deps import get_auth_service, get_rate_limiter
from snapland.api.v1.auth import get_current_user_id
from snapland.core.interfaces.services import RateLimitResult
from snapland.core.domain.user import User, TokenResponse

client = TestClient(app)

def mock_get_current_user_id():
    return uuid.UUID("11111111-1111-1111-1111-111111111111")

def mock_get_rate_limiter():
    limiter = MagicMock()
    limiter.check_limit = AsyncMock(return_value=RateLimitResult(allowed=True, retry_after_ms=0))
    return limiter

@pytest.fixture
def auth_service_mock():
    svc = MagicMock()
    svc.register = AsyncMock()
    svc.login = AsyncMock()
    svc.refresh_token = AsyncMock()
    svc.revoke_token = AsyncMock()
    svc.issue_ws_ticket = AsyncMock()
    return svc

@pytest.fixture(autouse=True)
def override_dependencies(auth_service_mock):
    app.dependency_overrides[get_current_user_id] = mock_get_current_user_id
    app.dependency_overrides[get_rate_limiter] = mock_get_rate_limiter
    app.dependency_overrides[get_auth_service] = lambda: auth_service_mock
    yield
    app.dependency_overrides = {}

def test_register(auth_service_mock):
    user_id = uuid.uuid4()
    auth_service_mock.register.return_value = User(id=user_id, email="test@test.com", display_name="Test")
    
    response = client.post("/api/v1/auth/register", json={
        "email": "test@test.com",
        "password": "password123",
        "display_name": "Test"
    })
    
    assert response.status_code == 200
    assert response.json()["email"] == "test@test.com"
    auth_service_mock.register.assert_called_once_with("test@test.com", "password123", "Test")

def test_login(auth_service_mock):
    auth_service_mock.login.return_value = TokenResponse(access_token="access", refresh_token="refresh")
    
    response = client.post("/api/v1/auth/login", json={
        "email": "test@test.com",
        "password": "password123"
    })
    
    assert response.status_code == 200
    assert response.json()["access_token"] == "access"
    assert "refresh_token" in response.cookies
    auth_service_mock.login.assert_called_once_with("test@test.com", "password123")

def test_refresh(auth_service_mock):
    auth_service_mock.refresh_token.return_value = TokenResponse(access_token="new_access", refresh_token="new_refresh")
    
    response = client.post("/api/v1/auth/refresh", cookies={"refresh_token": "old_refresh"})
    
    assert response.status_code == 200
    assert response.json()["access_token"] == "new_access"
    assert response.cookies["refresh_token"] == "new_refresh"
    auth_service_mock.refresh_token.assert_called_once_with("old_refresh")

def test_logout(auth_service_mock):
    response = client.post("/api/v1/auth/logout", cookies={"refresh_token": "old_refresh"})
    
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    auth_service_mock.revoke_token.assert_called_once_with("old_refresh")

def test_ws_ticket(auth_service_mock):
    auth_service_mock.issue_ws_ticket.return_value = "ticket123"
    
    response = client.post("/api/v1/auth/ws-ticket")
    
    assert response.status_code == 200
    assert response.json() == {"ticket": "ticket123"}
    auth_service_mock.issue_ws_ticket.assert_called_once()
