from fastapi.testclient import TestClient

from main import app
from snapland.config import Settings


def test_cors_preflight_allowed_origin():
    client = TestClient(app)
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"
    assert "POST" in response.headers.get("access-control-allow-methods", "")


def test_cors_simple_get_allowed_origin():
    client = TestClient(app)
    response = client.get(
        "/health/live",
        headers={"Origin": "http://localhost:5173"},
    )
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert response.headers.get("access-control-allow-credentials") == "true"


def test_cors_unallowed_origin_not_permitted():
    client = TestClient(app)
    response = client.get(
        "/health/live",
        headers={"Origin": "http://evil-attacker.example.com"},
    )
    assert response.status_code == 200
    # Disallowed origin must not have access-control-allow-origin header
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_origins_list_string_and_fallback():
    # Comma-separated string parsing
    s1 = Settings(CORS_ORIGINS="http://foo.com, http://bar.com")
    assert s1.cors_origins_list == ["http://foo.com", "http://bar.com"]

    # Fallback when empty string
    s2 = Settings(CORS_ORIGINS="")
    assert "http://localhost:5173" in s2.cors_origins_list
    assert "http://localhost:80" in s2.cors_origins_list
