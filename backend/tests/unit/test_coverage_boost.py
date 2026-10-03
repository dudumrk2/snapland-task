import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from snapland.api.deps import build_area_service, get_rate_limiter, get_redis
from snapland.api.v1.users import get_me
from snapland.core.domain.exceptions import NotFoundError
from snapland.core.domain.user import Session, User
from snapland.core.services.audit_service import AuditService
from snapland.infrastructure.db.repositories.session_repository import SessionRepository


@pytest.mark.asyncio
async def test_get_me_success() -> None:
    user_id = uuid.uuid4()
    mock_user = User(
        id=user_id,
        email="me@snapland.com",
        display_name="Me Tester",
        password_hash="pw_hash",
        created_at=datetime.now(timezone.utc),
    )
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = mock_user

    result = await get_me(user_id=user_id, user_repo=mock_repo)
    assert result.id == user_id
    assert result.email == "me@snapland.com"


@pytest.mark.asyncio
async def test_get_me_not_found() -> None:
    user_id = uuid.uuid4()
    mock_repo = AsyncMock()
    mock_repo.get_by_id.return_value = None

    with pytest.raises(NotFoundError):
        await get_me(user_id=user_id, user_repo=mock_repo)


@pytest.mark.asyncio
async def test_audit_service_log_event() -> None:
    audit_svc = AuditService()
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    mock_session_local = MagicMock()
    mock_session_local.return_value.__aenter__.return_value = mock_session

    with patch("snapland.infrastructure.db.session.SessionLocal", mock_session_local):
        await audit_svc.log_event(
            user_id=uuid.uuid4(),
            action="CREATE",
            entity_type="AREA",
            entity_id=uuid.uuid4(),
            payload={"name": "test"},
            ip_address="127.0.0.1",
        )
    mock_session.add.assert_called_once()
    mock_session.commit.assert_awaited_once()


def test_deps_helpers() -> None:
    mock_request = MagicMock()
    mock_request.app.state.redis = "fake_redis"
    mock_request.app.state.rate_limiter = "fake_limiter"

    assert get_redis(mock_request) == "fake_redis"
    assert get_rate_limiter(mock_request) == "fake_limiter"


def test_build_area_service() -> None:
    mock_session = AsyncMock()
    app_state = MagicMock()
    app_state.cache_repo = MagicMock()
    app_state.event_stream = MagicMock()

    service = build_area_service(mock_session, app_state)
    assert service is not None

    # Test missing cache repo
    bad_state = MagicMock()
    bad_state.cache_repo = None
    bad_state.redis = None
    with pytest.raises(RuntimeError, match="Cache repository is required"):
        build_area_service(mock_session, bad_state)


@pytest.mark.asyncio
async def test_session_repository_operations() -> None:
    mock_session = AsyncMock()
    mock_session.add = MagicMock()
    repo = SessionRepository(mock_session)

    session_id = uuid.uuid4()
    user_id = uuid.uuid4()
    family_id = uuid.uuid4()
    domain_session = Session(
        id=session_id,
        user_id=user_id,
        family_id=family_id,
        refresh_token_hash="hash_123",
        expires_at=datetime.now(timezone.utc),
        revoked_at=None,
        ip_address="127.0.0.1",
        created_at=datetime.now(timezone.utc),
    )

    # Test create
    created = await repo.create(domain_session)
    assert created.id == session_id
    mock_session.add.assert_called_once()
    assert mock_session.commit.await_count == 1

    # Test revoke
    await repo.revoke(session_id)
    assert mock_session.execute.await_count >= 1

    # Test revoke_family
    mock_exec_res = MagicMock()
    mock_exec_res.rowcount = 2
    mock_session.execute.return_value = mock_exec_res
    count = await repo.revoke_family(family_id)
    assert count == 2

    # Test revoke_all_for_user
    mock_session.execute.return_value = mock_exec_res
    count_user = await repo.revoke_all_for_user(user_id)
    assert count_user == 2


@pytest.mark.asyncio
async def test_cache_repository_crud() -> None:
    import fakeredis.aioredis

    from snapland.infrastructure.cache.cache_repository import CacheRepository

    fake_client = fakeredis.aioredis.FakeRedis()
    cache_repo = CacheRepository(fake_client)

    # test miss
    assert await cache_repo.get("test_key") is None
    assert await cache_repo.getdel("test_key") is None

    # test set and get
    await cache_repo.set("test_key", "hello", ttl_seconds=60)
    assert await cache_repo.get("test_key") == "hello"

    # test incr
    val = await cache_repo.incr("counter")
    assert val == 1

    # test getdel
    del_val = await cache_repo.getdel("test_key")
    assert del_val == "hello"
    assert await cache_repo.get("test_key") is None


def test_custom_exception_handlers() -> None:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from snapland.core.domain.exceptions import (
        AuthError,
        ConflictError,
        ForbiddenError,
        NotFoundError,
        ValidationError,
    )
    from snapland.middleware.error_handler import setup_error_handlers

    app = FastAPI()
    setup_error_handlers(app)

    @app.get("/error/val")
    def raise_val() -> None:
        raise ValidationError("invalid data")

    @app.get("/error/auth")
    def raise_auth() -> None:
        raise AuthError("auth failed")

    @app.get("/error/forbidden")
    def raise_forbid() -> None:
        raise ForbiddenError("no access")

    @app.get("/error/notfound")
    def raise_not_found() -> None:
        raise NotFoundError("missing")

    @app.get("/error/conflict")
    def raise_conflict() -> None:
        raise ConflictError("already exists")

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/error/val").status_code == 400
    assert client.get("/error/auth").status_code == 401
    assert client.get("/error/forbidden").status_code == 403
    assert client.get("/error/notfound").status_code == 404
    assert client.get("/error/conflict").status_code == 409

