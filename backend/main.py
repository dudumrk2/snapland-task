import asyncio
import logging
import sys
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from snapland.api.v1.areas import router as areas_router
from snapland.api.v1.auth import router as auth_router
from snapland.api.v1.health import router as health_router
from snapland.api.v1.users import router as users_router
from snapland.api.websocket.manager import WebSocketManager
from snapland.api.websocket.route import manager as ws_manager
from snapland.api.websocket.route import router as ws_router
from snapland.config import settings
from snapland.core.domain.ws_messages import UserLeftMessage, UserLeftPayload
from snapland.core.interfaces.realtime import Envelope, IEphemeralBus, IEventStream, IPresenceStore
from snapland.infrastructure.cache.cache_repository import CacheRepository
from snapland.infrastructure.pubsub.redis_presence import RedisPresenceStore
from snapland.infrastructure.pubsub.redis_pubsub import RedisEphemeralBus
from snapland.infrastructure.pubsub.redis_streams import RedisEventStream
from snapland.middleware.error_handler import setup_error_handlers
from snapland.middleware.rate_limiter import RateLimitMiddleware, RedisRateLimiter
from snapland.middleware.request_id import RequestIdMiddleware


def setup_logging():
    level = logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG

    structlog.configure(
        processors=[
            structlog.stdlib.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=level,
    )


setup_logging()
logger = structlog.get_logger(__name__)


async def supervise(name: str, app: FastAPI, worker_func):
    backoff = 1.0
    while True:
        start = asyncio.get_event_loop().time()
        try:
            if hasattr(app.state, "bg_tasks_status"):
                # Status=True only after the worker runs for at least 1 s without crashing.
                # A worker that crashes instantly would otherwise show as healthy.
                app.state.bg_tasks_status[name] = False
            await worker_func(app)
            await asyncio.sleep(0.5)
        except asyncio.CancelledError:
            break
        except Exception as e:
            if hasattr(app.state, "bg_tasks_status"):
                app.state.bg_tasks_status[name] = False
            logger.error(f"Background task {name} error, retrying...", exc_info=e, backoff=backoff)
            await asyncio.sleep(backoff)
            # Reset backoff only if the worker ran for a meaningful time (proved healthy).
            elapsed = asyncio.get_event_loop().time() - start
            if elapsed > 10.0:
                backoff = 1.0
            else:
                backoff = min(backoff * 2, 30.0)
        else:
            # Worker exited normally (e.g. async generator exhausted) — reset backoff.
            if hasattr(app.state, "bg_tasks_status"):
                app.state.bg_tasks_status[name] = True
            backoff = 1.0


async def run_ephemeral_subscriber(app: FastAPI):
    instance_id = settings.INSTANCE_ID
    ephemeral_bus: IEphemeralBus = app.state.ephemeral_bus
    manager: WebSocketManager = app.state.ws_manager
    async for envelope in ephemeral_bus.subscribe():
        if envelope.origin == instance_id:
            continue
        await manager.broadcast_ephemeral(envelope.message)
        # Mark as healthy once we're through the first iteration
        if hasattr(app.state, "bg_tasks_status"):
            app.state.bg_tasks_status["ephemeral_subscriber"] = True


async def run_control_subscriber(app: FastAPI):
    """Handles cross-instance control commands (e.g. logout) via a dedicated Redis channel."""
    from snapland.infrastructure.pubsub.redis_pubsub import RedisEphemeralBus
    import uuid as _uuid
    ephemeral_bus = app.state.ephemeral_bus
    if not hasattr(ephemeral_bus, "subscribe_control"):
        return
    manager: WebSocketManager = app.state.ws_manager
    async for cmd in ephemeral_bus.subscribe_control():
        try:
            cmd_type = cmd.get("type")
            if cmd_type == "logout":
                user_id_str = cmd.get("userId")
                if user_id_str:
                    user_id = _uuid.UUID(user_id_str)
                    await manager.disconnect_user(user_id)
                    if hasattr(app.state, "bg_tasks_status"):
                        app.state.bg_tasks_status["control_subscriber"] = True
        except Exception as e:
            logger.warning("Control subscriber error processing command", cmd=cmd, exc_info=e)




async def run_stream_follower(app: FastAPI):
    event_stream: IEventStream = app.state.event_stream
    manager: WebSocketManager = app.state.ws_manager

    # Persist last_id across restarts so we never skip events written during an outage.
    # On the very first run (or after a Redis full flush), start from current tip.
    if not hasattr(app.state, "_stream_last_id") or app.state._stream_last_id is None:
        app.state._stream_last_id = None  # will be resolved by follow()

    async for event_id, message in event_stream.follow(resume_from=app.state._stream_last_id):
        app.state._stream_last_id = event_id
        if hasattr(message, "eventId"):
            message.eventId = event_id
        await manager.broadcast_durable(message)


async def run_presence_reaper(app: FastAPI):
    while True:
        await asyncio.sleep(10)
        presence_store: IPresenceStore = app.state.presence_store
        manager: WebSocketManager = app.state.ws_manager
        ephemeral_bus = getattr(app.state, "ephemeral_bus", None)
        expired_user_ids = await presence_store.reap_expired()
        for user_id in expired_user_ids:
            left_msg = UserLeftMessage(payload=UserLeftPayload(userId=user_id))
            await manager.broadcast_ephemeral(left_msg)
            if ephemeral_bus:
                await ephemeral_bus.publish(Envelope(origin=settings.INSTANCE_ID, message=left_msg))


async def run_presence_heartbeat(app: FastAPI):
    while True:
        await asyncio.sleep(10)
        presence_store: IPresenceStore = app.state.presence_store
        manager: WebSocketManager = app.state.ws_manager
        conns = list(manager.active_connections.items())
        if conns:
            items = []
            for conn_id, conn in conns:
                user = getattr(conn, "user", None)
                display_name = user.display_name if user else "User"
                items.append((conn.user_id, conn_id, display_name))
            if hasattr(presence_store, "heartbeat_batch"):
                await presence_store.heartbeat_batch(items)
            else:
                for uid, cid, dname in items:
                    await presence_store.heartbeat(uid, cid, dname)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Application starting up", instance_id=settings.INSTANCE_ID)

    if not hasattr(app.state, "db_engine") or app.state.db_engine is None:
        app.state.db_engine = create_async_engine(settings.DATABASE_URL)
    if not hasattr(app.state, "redis") or app.state.redis is None:
        app.state.redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    if not hasattr(app.state, "cache_repo") or app.state.cache_repo is None:
        app.state.cache_repo = CacheRepository(app.state.redis)
    if not hasattr(app.state, "rate_limiter") or app.state.rate_limiter is None:
        app.state.rate_limiter = RedisRateLimiter(app.state.redis)

    if not hasattr(app.state, "ephemeral_bus") or app.state.ephemeral_bus is None:
        app.state.ephemeral_bus = RedisEphemeralBus(app.state.redis)
    if not hasattr(app.state, "event_stream") or app.state.event_stream is None:
        app.state.event_stream = RedisEventStream(app.state.redis)
    if not hasattr(app.state, "presence_store") or app.state.presence_store is None:
        app.state.presence_store = RedisPresenceStore(app.state.redis)
    if not hasattr(app.state, "ws_manager") or app.state.ws_manager is None:
        app.state.ws_manager = ws_manager

    if not hasattr(app.state, "session_factory") or app.state.session_factory is None:
        app.state.session_factory = async_sessionmaker(app.state.db_engine, class_=AsyncSession, expire_on_commit=False)

    app.state.bg_tasks_status = {
        "ephemeral_subscriber": False,
        "control_subscriber": False,
        "stream_follower": False,
        "presence_reaper": False,
        "presence_heartbeat": False,
    }

    tasks = [
        asyncio.create_task(supervise("ephemeral_subscriber", app, run_ephemeral_subscriber)),
        asyncio.create_task(supervise("control_subscriber", app, run_control_subscriber)),
        asyncio.create_task(supervise("stream_follower", app, run_stream_follower)),
        asyncio.create_task(supervise("presence_reaper", app, run_presence_reaper)),
        asyncio.create_task(supervise("presence_heartbeat", app, run_presence_heartbeat)),
    ]

    try:
        yield
    finally:
        logger.info("Application shutting down", instance_id=settings.INSTANCE_ID)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

        if hasattr(app.state, "redis") and app.state.redis:
            await app.state.redis.aclose()
        if hasattr(app.state, "db_engine") and app.state.db_engine:
            await app.state.db_engine.dispose()


app = FastAPI(title="Snapland API", lifespan=lifespan)

app.add_middleware(RequestIdMiddleware)
app.add_middleware(RateLimitMiddleware)
setup_error_handlers(app)

app.include_router(health_router)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(areas_router, prefix="/api/v1")
app.include_router(users_router, prefix="/api/v1")
app.include_router(ws_router)
