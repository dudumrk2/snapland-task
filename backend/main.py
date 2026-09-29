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
from snapland.core.interfaces.realtime import IEphemeralBus, IEventStream, IPresenceStore
from snapland.infrastructure.cache.cache_repository import CacheRepository
from snapland.infrastructure.db.repositories.user_repository import UserRepository
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
            structlog.processors.JSONRenderer()
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


async def run_ephemeral_subscriber(app: FastAPI):
    ephemeral_bus: IEphemeralBus = app.state.ephemeral_bus
    manager: WebSocketManager = app.state.ws_manager
    instance_id = settings.INSTANCE_ID

    try:
        async for envelope in ephemeral_bus.subscribe():
            # HLD §9.2 Multi-instance echo prevention: skip envelopes matching local INSTANCE_ID
            if envelope.origin == instance_id:
                continue
            await manager.broadcast_ephemeral(envelope.message)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Ephemeral subscriber error", exc_info=e)


async def run_stream_follower(app: FastAPI):
    event_stream: IEventStream = app.state.event_stream
    manager: WebSocketManager = app.state.ws_manager

    try:
        async for event_id, message in event_stream.follow():
            if hasattr(message, "eventId"):
                message.eventId = event_id
            await manager.broadcast_durable(message)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Stream follower error", exc_info=e)


async def run_presence_reaper(app: FastAPI):
    presence_store: IPresenceStore = app.state.presence_store
    manager: WebSocketManager = app.state.ws_manager

    try:
        while True:
            await asyncio.sleep(10)
            expired_user_ids = await presence_store.reap_expired()
            for user_id in expired_user_ids:
                left_msg = UserLeftMessage(payload=UserLeftPayload(userId=user_id))
                await manager.broadcast_ephemeral(left_msg)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Presence reaper error", exc_info=e)


async def run_presence_heartbeat(app: FastAPI):
    presence_store: IPresenceStore = app.state.presence_store
    manager: WebSocketManager = app.state.ws_manager

    try:
        while True:
            await asyncio.sleep(10)
            for conn_id, conn in list(manager.active_connections.items()):
                user = getattr(conn, "user", None)
                display_name = user.display_name if user else "User"
                await presence_store.heartbeat(conn.user_id, conn_id, display_name)
    except asyncio.CancelledError:
        pass
    except Exception as e:
        logger.error("Presence heartbeat error", exc_info=e)


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

    if not hasattr(app.state, "user_repo") or app.state.user_repo is None:
        session_factory = async_sessionmaker(app.state.db_engine, class_=AsyncSession, expire_on_commit=False)
        app.state.user_repo = UserRepository(session_factory())

    tasks = [
        asyncio.create_task(run_ephemeral_subscriber(app)),
        asyncio.create_task(run_stream_follower(app)),
        asyncio.create_task(run_presence_reaper(app)),
        asyncio.create_task(run_presence_heartbeat(app)),
    ]

    yield

    logger.info("Application shutting down", instance_id=settings.INSTANCE_ID)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)

    if hasattr(app.state, "redis"):
        await app.state.redis.aclose()
    if hasattr(app.state, "db_engine"):
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
