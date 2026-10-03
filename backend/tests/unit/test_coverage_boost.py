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
    from snapland.core.services.area_service import AreaService

    mock_session = AsyncMock()
    app_state = MagicMock()
    app_state.cache_repo = MagicMock()
    app_state.event_stream = MagicMock()

    service = build_area_service(mock_session, app_state)
    assert isinstance(service, AreaService)

    # Test missing cache repo
    bad_state = MagicMock()
    bad_state.cache_repo = None
    bad_state.redis = None
    with pytest.raises(RuntimeError, match="Cache repository is required"):
        build_area_service(mock_session, bad_state)

    # Test missing event stream
    bad_state_events = MagicMock()
    bad_state_events.cache_repo = MagicMock()
    bad_state_events.event_stream = None
    bad_state_events.redis = None
    with pytest.raises(RuntimeError, match="Event stream publisher is required"):
        build_area_service(mock_session, bad_state_events)


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

    # Reset mock for revoke
    mock_session.reset_mock()

    # Test revoke
    await repo.revoke(session_id)
    assert mock_session.execute.await_count == 1

    # Reset mock for revoke_family
    mock_session.reset_mock()
    mock_exec_res = MagicMock()
    mock_exec_res.rowcount = 2
    mock_session.execute.return_value = mock_exec_res
    count = await repo.revoke_family(family_id)
    assert count == 2
    assert mock_session.execute.await_count == 1

    # Reset mock for revoke_all_for_user
    mock_session.reset_mock()
    mock_session.execute.return_value = mock_exec_res
    count_user = await repo.revoke_all_for_user(user_id)
    assert count_user == 2
    assert mock_session.execute.await_count == 1


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


@pytest.mark.asyncio
async def test_user_repository_methods() -> None:
    from snapland.infrastructure.db.models import UserModel
    from snapland.infrastructure.db.repositories.user_repository import UserRepository

    mock_session = AsyncMock()
    repo = UserRepository(mock_session)

    uid = uuid.uuid4()
    domain_user = User(
        id=uid,
        email="test@snapland.com",
        display_name="Tester",
        password_hash="hashed",
    )

    # 1. create
    created = await repo.create(domain_user)
    assert created.id == uid
    mock_session.add.assert_called_once()
    assert mock_session.commit.await_count == 1

    # 2. get_by_id (found)
    mock_model = UserModel(
        id=uid,
        email="test@snapland.com",
        display_name="Tester",
        password_hash="hashed",
    )
    with patch.object(repo, "get_by_id", new_callable=AsyncMock) as mock_get_id:
        mock_get_id.return_value = domain_user
        u = await repo.get_by_id(uid)
        assert u is not None and u.id == uid

    # 3. get_by_email
    mock_res = MagicMock()
    mock_res.scalar_one_or_none.return_value = mock_model
    mock_session.execute.return_value = mock_res
    u_email = await repo.get_by_email("test@snapland.com")
    assert u_email is not None and u_email.email == "test@snapland.com"

    # 4. get_by_email (not found)
    mock_res.scalar_one_or_none.return_value = None
    u_none = await repo.get_by_email("none@snapland.com")
    assert u_none is None


@pytest.mark.asyncio
async def test_health_ready_branches() -> None:
    from fastapi import FastAPI, Response

    from snapland.api.v1.health import health_ready

    app = FastAPI()

    # Case 1: DB healthy, Redis healthy
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock()

    mock_redis = AsyncMock()
    mock_redis.ping = AsyncMock(return_value=True)

    app.state.db_engine = mock_engine
    app.state.redis = mock_redis
    app.state.bg_tasks_status = {"retention": True}

    # Direct handler testing
    req = MagicMock()
    req.app.state.db_engine = mock_engine
    req.app.state.redis = mock_redis
    req.app.state.bg_tasks_status = {"retention": True}
    res = Response()

    health_res = await health_ready(req, res)
    assert health_res.status == "healthy"
    assert health_res.database == "ok"
    assert health_res.redis == "ok"
    assert res.status_code == 200

    # Case 2: DB failure
    mock_engine.connect.side_effect = Exception("DB Connection Refused")
    res_db_fail = Response()
    health_res_db_fail = await health_ready(req, res_db_fail)
    assert health_res_db_fail.status == "unhealthy"
    assert health_res_db_fail.database == "down"
    assert res_db_fail.status_code == 503

    # Case 3: Redis failure (DB ok)
    mock_engine.connect.side_effect = None
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_redis.ping.side_effect = Exception("Redis Down")
    res_redis_fail = Response()
    health_res_redis_fail = await health_ready(req, res_redis_fail)
    assert health_res_redis_fail.status == "degraded"
    assert health_res_redis_fail.redis == "down"
    assert res_redis_fail.status_code == 503

    # Case 4: Degraded background tasks
    mock_redis.ping.side_effect = None
    req.app.state.bg_tasks_status = {"retention": False}
    res_bg_fail = Response()
    health_res_bg_fail = await health_ready(req, res_bg_fail)
    assert health_res_bg_fail.status == "degraded"
    assert res_bg_fail.status_code == 200


@pytest.mark.asyncio
async def test_auth_route_helpers() -> None:
    from snapland.api.v1.auth import get_client_ip, get_current_user_id
    from snapland.core.domain.exceptions import AuthError

    # 1. get_client_ip
    req_forwarded = MagicMock()
    req_forwarded.headers.get.side_effect = lambda k: "203.0.113.195, 70.41.3.18" if k == "X-Forwarded-For" else None
    assert get_client_ip(req_forwarded) == "203.0.113.195"

    req_direct = MagicMock()
    req_direct.headers.get.return_value = None
    req_direct.client.host = "192.168.1.50"
    assert get_client_ip(req_direct) == "192.168.1.50"

    # 2. get_current_user_id - missing header
    req_no_auth = MagicMock()
    req_no_auth.headers.get.return_value = None
    with pytest.raises(AuthError, match="Missing or invalid token"):
        await get_current_user_id(req_no_auth, AsyncMock())

    # 3. get_current_user_id - valid token
    req_auth = MagicMock()
    req_auth.headers.get.return_value = "Bearer valid_token"
    mock_auth_svc = MagicMock()
    uid = uuid.uuid4()
    mock_auth_svc.verify_access_token.return_value = uid

    resolved_id = await get_current_user_id(req_auth, mock_auth_svc)
    assert resolved_id == uid

    # 4. get_current_user_id - invalid token
    mock_auth_svc.verify_access_token.side_effect = Exception("Signature verification failed")
    with pytest.raises(AuthError, match="Token not verified"):
        await get_current_user_id(req_auth, mock_auth_svc)


@pytest.mark.asyncio
async def test_area_service_validation_failure() -> None:
    from snapland.core.domain.area import Coordinate, CreateAreaRequest
    from snapland.core.domain.exceptions import ValidationError
    from snapland.core.services.area_service import AreaService

    mock_spatial = MagicMock()
    mock_val = MagicMock()
    mock_val.valid = False
    mock_val.reason = "Self-intersecting polygon"
    mock_spatial.validate_polygon.return_value = mock_val

    svc = AreaService(
        repo=AsyncMock(),
        spatial=mock_spatial,
        cache=AsyncMock(),
        events=AsyncMock(),
        audit=AsyncMock(),
    )

    req = CreateAreaRequest(
        name="Invalid Polygon",
        coordinates=[
            Coordinate(lat=0.0, lng=0.0),
            Coordinate(lat=1.0, lng=1.0),
            Coordinate(lat=0.0, lng=1.0),
            Coordinate(lat=0.0, lng=0.0),
        ],
    )

    with pytest.raises(ValidationError, match="Invalid polygon"):
        await svc.create_area(req, uuid.uuid4())


@pytest.mark.asyncio
async def test_area_service_crud_operations() -> None:
    from snapland.core.domain.area import Area, Coordinate, CreateAreaRequest, UpdateAreaRequest
    from snapland.core.domain.exceptions import ConflictError, NotFoundError
    from snapland.core.services.area_service import AreaService

    mock_repo = AsyncMock()
    mock_spatial = MagicMock()
    mock_val = MagicMock()
    mock_val.valid = True
    mock_spatial.validate_polygon.return_value = mock_val
    mock_spatial.calculate_area_km2.return_value = 5.25

    mock_cache = AsyncMock()
    mock_events = AsyncMock()
    mock_audit = AsyncMock()

    svc = AreaService(
        repo=mock_repo,
        spatial=mock_spatial,
        cache=mock_cache,
        events=mock_events,
        audit=mock_audit,
    )

    uid = uuid.uuid4()
    area_id = uuid.uuid4()
    coords = [
        Coordinate(lat=32.0, lng=34.0),
        Coordinate(lat=32.1, lng=34.0),
        Coordinate(lat=32.1, lng=34.1),
        Coordinate(lat=32.0, lng=34.0),
    ]

    saved_area = Area(
        id=area_id,
        name="Test Park",
        coordinates=coords,
        area_km2=5.25,
        version=1,
        created_by=uid,
        last_edited_by=uid,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_repo.create.return_value = saved_area
    mock_repo.get_by_id.return_value = saved_area

    # 1. create_area success
    created = await svc.create_area(CreateAreaRequest(name="Test Park", coordinates=coords), uid)
    assert created.id == area_id
    mock_repo.create.assert_awaited_once()
    mock_cache.incr.assert_awaited_once_with("areas:epoch")
    mock_events.publish.assert_awaited_once()

    # 2. update_area success
    updated_area = Area(
        id=area_id,
        name="Renamed Park",
        coordinates=coords,
        area_km2=5.25,
        version=2,
        created_by=uid,
        last_edited_by=uid,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    mock_repo.update.return_value = updated_area
    res_updated = await svc.update_area(
        area_id,
        UpdateAreaRequest(name="Renamed Park", version=1),
        uid,
    )
    assert res_updated.version == 2

    # 3. update_area OCC conflict
    with pytest.raises(ConflictError):
        await svc.update_area(
            area_id,
            UpdateAreaRequest(name="Conflict Park", version=99),
            uid,
        )

    # 4. update_area not found
    mock_repo.get_by_id.return_value = None
    with pytest.raises(NotFoundError):
        await svc.update_area(
            area_id,
            UpdateAreaRequest(name="Missing", version=1),
            uid,
        )

    # 5. delete_area success
    await svc.delete_area(area_id, user_id=uid)
    mock_repo.soft_delete.assert_awaited_once_with(area_id, uid)
    mock_cache.incr.assert_awaited_with("areas:epoch")
    mock_events.publish.assert_awaited()


@pytest.mark.asyncio
async def test_health_db_branches() -> None:
    from snapland.api.v1.health import health_db

    # 1. Healthy index plan
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_conn.execute = AsyncMock(
        return_value=MagicMock(fetchall=lambda: [("Bitmap Index Scan on areas_geom_gist (cost=0.00..4.12)",)])
    )
    mock_conn.begin.return_value.__aenter__ = AsyncMock()
    mock_conn.begin.return_value.__aexit__ = AsyncMock()
    mock_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_engine.connect.return_value.__aexit__ = AsyncMock()

    req = MagicMock()
    req.app.state.db_engine = mock_engine

    res_ok = await health_db(req)
    assert res_ok["status"] == "ok"
    assert res_ok["index_used"] == "areas_geom_gist"

    # 2. Query execution failure
    mock_conn.execute.side_effect = Exception("Database timeout")
    res_err = await health_db(req)
    assert res_err.status_code == 500


@pytest.mark.asyncio
async def test_auth_logout_and_ws_ticket() -> None:
    from fastapi import Response

    from snapland.api.v1.auth import logout, ws_ticket

    uid = uuid.uuid4()
    mock_auth_svc = AsyncMock()
    mock_auth_svc.revoke_token.return_value = uid
    mock_auth_svc.issue_ws_ticket.return_value = "ticket_xyz_123"

    req = MagicMock()
    req.headers.get.return_value = None
    req.app.state.ws_manager = AsyncMock()
    req.app.state.ephemeral_bus = AsyncMock()
    res = Response()

    # 1. logout with refresh_token
    logout_res = await logout(req, res, refresh_token="valid_refresh", auth_svc=mock_auth_svc)
    assert logout_res == {"status": "ok"}
    mock_auth_svc.revoke_token.assert_awaited_once_with("valid_refresh")

    # 2. ws_ticket
    ticket_res = await ws_ticket(user_id=uid, auth_svc=mock_auth_svc)
    assert ticket_res == {"ticket": "ticket_xyz_123"}
    mock_auth_svc.issue_ws_ticket.assert_awaited_once_with(uid)


@pytest.mark.asyncio
async def test_deps_database_and_services() -> None:
    from snapland.api.deps import (
        build_area_service,
        get_area_service,
        get_audit_service,
        get_auth_service,
        get_db,
    )

    # 1. get_db success
    mock_session = AsyncMock()
    mock_session_maker = MagicMock()
    mock_session_maker.return_value.__aenter__.return_value = mock_session
    mock_session_maker.return_value.__aexit__ = AsyncMock()

    with patch("snapland.api.deps.SessionLocal", mock_session_maker):
        db_gen = get_db()
        yielded_session = await anext(db_gen)
        assert yielded_session == mock_session
        try:
            await anext(db_gen)
        except StopAsyncIteration:
            pass
        mock_session.commit.assert_awaited_once()

    # 2. get_db rollback on exception
    with patch("snapland.api.deps.SessionLocal", mock_session_maker):
        db_gen = get_db()
        await anext(db_gen)
        try:
            await db_gen.athrow(RuntimeError("DB query failed"))
        except (RuntimeError, StopAsyncIteration):
            pass
        mock_session.rollback.assert_awaited_once()

    # 3. get_auth_service
    auth_svc = get_auth_service(db=AsyncMock(), redis=MagicMock())
    assert auth_svc is not None

    # 4. get_audit_service
    assert get_audit_service() is not None

    # 5. build_area_service with redis fallback
    mock_redis = MagicMock()
    app_state_redis = MagicMock()
    app_state_redis.cache_repo = None
    app_state_redis.event_stream = None
    app_state_redis.redis = mock_redis

    built_svc = build_area_service(AsyncMock(), app_state_redis)
    assert built_svc is not None

    # 6. get_area_service
    mock_req = MagicMock()
    mock_req.app.state = app_state_redis
    assert get_area_service(mock_req, AsyncMock()) is not None


def test_metrics_helpers() -> None:
    from snapland.middleware.metrics import get_route_template, update_db_pool_metrics

    # 1. update_db_pool_metrics
    app = MagicMock()
    mock_pool = MagicMock()
    mock_pool.checkedout.return_value = 4
    mock_pool.checkedin.return_value = 16
    app.state.db_engine.pool = mock_pool

    update_db_pool_metrics(app)

    # 2. get_route_template from route scope
    req_route = MagicMock()
    mock_route = MagicMock()
    mock_route.path = "/api/v1/areas/{id}"
    req_route.scope = {"route": mock_route}
    assert get_route_template(req_route) == "/api/v1/areas/{id}"

    # 3. get_route_template unmatched
    req_unmatched = MagicMock()
    req_unmatched.scope = {}
    req_unmatched.app.routes = []
    assert get_route_template(req_unmatched) == "unmatched"


@pytest.mark.asyncio
async def test_websocket_handlers_basics() -> None:
    from snapland.api.websocket.handlers import _validate_coordinate, dispatch_message
    from snapland.core.domain.ws_messages import PongMessage

    # 1. _validate_coordinate
    assert _validate_coordinate("not_a_dict") is None
    assert _validate_coordinate({"lat": 32.0}) is None
    assert _validate_coordinate({"lng": 34.0}) is None
    assert _validate_coordinate({"lat": 100.0, "lng": 34.0}) is None
    assert _validate_coordinate({"lat": "invalid", "lng": 34.0}) is None

    valid = _validate_coordinate({"lat": "32.05", "lng": "34.78"})
    assert valid is not None
    assert valid.lat == 32.05
    assert valid.lng == 34.78

    # 2. dispatch_message invalid JSON
    mock_conn = AsyncMock()
    await dispatch_message(mock_conn, "{not_valid_json", MagicMock())
    mock_conn.enqueue.assert_awaited_once()

    # 3. dispatch_message non-dict JSON
    mock_conn.reset_mock()
    await dispatch_message(mock_conn, '"just_a_string"', MagicMock())
    mock_conn.enqueue.assert_awaited_once()

    # 4. dispatch_message PING -> PONG
    mock_conn.reset_mock()
    await dispatch_message(mock_conn, '{"type": "PING"}', MagicMock())
    mock_conn.enqueue.assert_awaited_once()
    sent_msg = mock_conn.enqueue.call_args[0][0]
    assert isinstance(sent_msg, PongMessage)

    # 5. dispatch_message PONG
    mock_conn.reset_mock()
    await dispatch_message(mock_conn, '{"type": "PONG"}', MagicMock())
    mock_conn.enqueue.assert_not_called()
    assert mock_conn.last_ping_time is None

    # 6. dispatch_message CURSOR_MOVE
    mock_conn.reset_mock()
    mock_conn.user_id = uuid.uuid4()
    mock_conn.last_cursor_time = 0.0
    mock_conn.throttle_cursor = MagicMock(return_value=True)
    app_state_bus = MagicMock()
    app_state_bus.rate_limiter = None
    app_state_bus.ephemeral_bus = AsyncMock()
    app_state_bus.ws_manager = AsyncMock()
    await dispatch_message(
        mock_conn,
        '{"type": "CURSOR_MOVE", "payload": {"lat": 32.0, "lng": 34.0}}',
        app_state_bus,
    )
    app_state_bus.ephemeral_bus.publish.assert_awaited_once()





