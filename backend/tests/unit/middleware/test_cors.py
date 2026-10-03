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
    assert s2.cors_origins_list == [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:80",
        "http://127.0.0.1:80",
        "http://localhost",
        "http://127.0.0.1",
    ]

    # JSON array string parsing
    s3 = Settings(CORS_ORIGINS='["http://alpha.com", "http://beta.com"]')
    assert s3.cors_origins_list == ["http://alpha.com", "http://beta.com"]


def test_cors_preflight_unallowed_origin():
    client = TestClient(app)
    response = client.options(
        "/api/v1/auth/login",
        headers={
            "Origin": "http://evil-attacker.example.com",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type",
        },
    )
    # Disallowed origin in preflight should not receive allow-origin
    assert response.headers.get("access-control-allow-origin") is None


def test_cors_wildcard_rejected_in_production():
    import pytest
    with pytest.raises(ValueError, match="CORS_ORIGINS cannot contain"):
        Settings(
            ENVIRONMENT="production",
            CORS_ORIGINS="*",
            WS_ALLOWED_ORIGINS="http://example.com",
            JWT_PRIVATE_KEY="-----BEGIN RSA PRIVATE KEY-----\nMIIE...",
            JWT_PUBLIC_KEY="-----BEGIN RSA PUBLIC KEY-----\nMIIB...",
            DATABASE_URL="postgresql+asyncpg://user:pass@prod-db:5432/db",
        )
