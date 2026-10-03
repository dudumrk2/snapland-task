import asyncio
import uuid
from typing import Optional

import structlog
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from snapland.api.websocket.handlers import dispatch_message
from snapland.api.websocket.manager import WebSocketManager
from snapland.config import settings
from snapland.core.domain.ws_messages import (
    ErrorMessage,
    ErrorPayload,
    PresenceSnapshotMessage,
    PresenceSnapshotPayload,
    PresenceUser,
    ResyncRequiredMessage,
    ResyncRequiredPayload,
    UserJoinedMessage,
    UserJoinedPayload,
    UserLeftMessage,
    UserLeftPayload,
)
from snapland.core.interfaces.realtime import Envelope

logger = structlog.get_logger(__name__)

router = APIRouter()
manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str,
    lastEventId: Optional[str] = None,
) -> None:
    # 1. Origin check before accepting connection
    origin = websocket.headers.get("origin")
    allowed_origins = settings.WS_ALLOWED_ORIGINS
    if allowed_origins != "*":
        allowed_list = [o.strip() for o in allowed_origins.split(",") if o.strip()]
        if not origin or origin not in allowed_list:
            await websocket.close(code=4003)
            return

    # 2. Validate ticket via atomic GETDEL in CacheRepository
    cache_repo = getattr(websocket.app.state, "cache_repo", None)
    if not cache_repo and hasattr(websocket.app.state, "redis"):
        from snapland.infrastructure.cache.cache_repository import CacheRepository
        cache_repo = CacheRepository(websocket.app.state.redis)

    user_id_str = await cache_repo.getdel(f"ws_ticket:{ticket}") if cache_repo else None
    if not user_id_str:
        await websocket.close(code=4001)
        return

    try:
        user_id = uuid.UUID(user_id_str)
    except Exception:
        await websocket.close(code=4001)
        return

    # 3. Connect to manager (initially unregistered from live broadcast pool per HLD §9.6.3)
    active_manager: WebSocketManager = getattr(websocket.app.state, "ws_manager", None) or manager

    conn_id = str(uuid.uuid4())
    structlog.contextvars.bind_contextvars(conn_id=conn_id, user_id=str(user_id))
    conn = await active_manager.connect(websocket, user_id, conn_id, register=False)
    if not conn:
        return

    presence_store = getattr(websocket.app.state, "presence_store", None)
    ephemeral_bus = getattr(websocket.app.state, "ephemeral_bus", None)
    ttl_task: Optional[asyncio.Task] = None

    try:
        # 4. Resolve user display name (scoped session avoids connection pool leak)
        display_name = "User"
        user_repo = getattr(websocket.app.state, "user_repo", None)
        if user_repo:
            try:
                user = await user_repo.get_by_id(user_id)
                if user:
                    display_name = user.display_name
                    conn.user = user
            except Exception:
                pass
        elif hasattr(websocket.app.state, "session_factory") and websocket.app.state.session_factory:
            try:
                from snapland.infrastructure.db.repositories.user_repository import UserRepository
                async with websocket.app.state.session_factory() as session:
                    repo = UserRepository(session)
                    user = await repo.get_by_id(user_id)
                    if user:
                        display_name = user.display_name
                        conn.user = user
            except Exception:
                pass

        # 5. Presence: register connection, send snapshot, broadcast joined if first connection
        if presence_store:
            try:
                is_first = await presence_store.add_connection(user_id, conn_id, display_name)
                users = await presence_store.snapshot()
                snapshot_msg = PresenceSnapshotMessage(
                    payload=PresenceSnapshotPayload(users=list(users))
                )
                await conn.enqueue(snapshot_msg)

                if is_first:
                    joined_msg = UserJoinedMessage(
                        payload=UserJoinedPayload(
                            user=PresenceUser(userId=user_id, displayName=display_name)
                        )
                    )
                    await active_manager.broadcast_ephemeral(joined_msg, exclude_conn_id=conn_id)
                    if ephemeral_bus:
                        await ephemeral_bus.publish(Envelope(origin=settings.INSTANCE_ID, message=joined_msg))
            except Exception as e:
                logger.warning("Presence error on join", exc_info=e)

        # 6. Event stream catch-up / replay if lastEventId is provided
        last_replayed_id: Optional[str] = lastEventId
        event_stream = getattr(websocket.app.state, "event_stream", None) if lastEventId else None
        if event_stream and lastEventId:
            # Cap replay at the queue bound so we never overfill it and close the socket.
            # read_since returns resync_required=True when more than `limit` events exist.
            REPLAY_LIMIT = conn.queue.maxsize - 1  # leave room for RESYNC_REQUIRED itself
            try:
                catchup = await event_stream.read_since(lastEventId, limit=REPLAY_LIMIT)
                if catchup.resync_required:
                    await conn.enqueue(
                        ResyncRequiredMessage(payload=ResyncRequiredPayload(reason="stream_trimmed"))
                    )
                else:
                    for event_id, msg in catchup.events:
                        last_replayed_id = event_id
                        if hasattr(msg, "eventId"):
                            msg.eventId = event_id
                        await conn.enqueue(msg)
            except Exception as e:
                logger.warning("Catch-up replay error", exc_info=e)

        # 7. Register connection into live broadcast pool after initial catch-up is queued
        active_manager.register(conn)

        # 7b. Replay gap check: catch any events published between read_since and register()
        # conn.seen_event_ids automatically de-duplicates any live broadcast events.
        if event_stream and last_replayed_id and not conn.closed:
            try:
                gap_catchup = await event_stream.read_since(last_replayed_id, limit=conn.queue.maxsize - 1)
                if not gap_catchup.resync_required:
                    for event_id, msg in gap_catchup.events:
                        if hasattr(msg, "eventId"):
                            msg.eventId = event_id
                        await conn.enqueue(msg)
            except Exception as e:
                logger.warning("Gap replay error", exc_info=e)

        # 8. Connection TTL Task: close with code 4401 after token lifespan
        ttl_seconds = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60

        async def connection_ttl_timer():
            try:
                await asyncio.sleep(ttl_seconds)
                if not conn.closed:
                    conn.closed = True
                    await websocket.close(code=4401, reason="token_expired")
            except asyncio.CancelledError:
                pass

        ttl_task = asyncio.create_task(connection_ttl_timer())

        # 9. Main receive loop
        while not conn.closed:
            data = await websocket.receive_text()
            # Inbound 64 KB limit check
            if len(data) > 65536 or len(data.encode("utf-8")) > 65536:
                conn.closed = True
                await websocket.close(code=1009, reason="Message too large")
                break

            try:
                await dispatch_message(conn, data, websocket.app.state)
            except Exception as e:
                logger.warning("Message dispatch exception", conn_id=conn.conn_id, error=str(e))
                await conn.enqueue(
                    ErrorMessage(payload=ErrorPayload(code="INTERNAL_ERROR", message="Internal processing error"))
                )

    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket receive loop closed", exc_info=e)
    finally:
        if ttl_task and not ttl_task.done():
            ttl_task.cancel()

        async def _disconnect_cleanup():
            await active_manager.disconnect(conn_id)
            if presence_store:
                try:
                    is_last = await presence_store.remove(user_id, conn_id)
                    if is_last:
                        left_msg = UserLeftMessage(payload=UserLeftPayload(userId=user_id))
                        await active_manager.broadcast_ephemeral(left_msg)
                        if ephemeral_bus:
                            await ephemeral_bus.publish(Envelope(origin=settings.INSTANCE_ID, message=left_msg))
                except Exception as e:
                    logger.warning("Presence error on disconnect", exc_info=e)

        try:
            await asyncio.shield(_disconnect_cleanup())
        except asyncio.CancelledError:
            await _disconnect_cleanup()
