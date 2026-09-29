import asyncio
import logging
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from snapland.api.websocket.handlers import dispatch_message
from snapland.api.websocket.manager import WebSocketManager
from snapland.config import settings
from snapland.core.domain.ws_messages import (
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

logger = logging.getLogger(__name__)

router = APIRouter()

# Global manager instance for this FastAPI worker
manager = WebSocketManager()


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    ticket: str,
    lastEventId: Optional[str] = None
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

    # 3. Connect to manager
    conn_id = str(uuid.uuid4())
    conn = await manager.connect(websocket, user_id, conn_id)

    # 4. Resolve user display name
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

    # 5. Presence: register heartbeat, send snapshot, broadcast joined
    presence_store = getattr(websocket.app.state, "presence_store", None)
    if presence_store:
        try:
            await presence_store.heartbeat(user_id, conn_id, display_name)
            users = await presence_store.snapshot()
            snapshot_msg = PresenceSnapshotMessage(
                payload=PresenceSnapshotPayload(users=list(users))
            )
            await conn.enqueue(snapshot_msg)

            joined_msg = UserJoinedMessage(
                payload=UserJoinedPayload(
                    user=PresenceUser(user_id=user_id, display_name=display_name)
                )
            )
            await manager.broadcast_ephemeral(joined_msg, exclude_conn_id=conn_id)
        except Exception as e:
            logger.warning("Presence error on join", exc_info=e)

    # 6. Event stream catch-up / replay if lastEventId is provided
    if lastEventId:
        event_stream = getattr(websocket.app.state, "event_stream", None)
        if event_stream:
            try:
                catchup = await event_stream.read_since(lastEventId)
                if catchup.resync_required:
                    await conn.enqueue(
                        ResyncRequiredMessage(payload=ResyncRequiredPayload(reason="stream_trimmed"))
                    )
                else:
                    for event_id, msg in catchup.events:
                        if hasattr(msg, "eventId"):
                            msg.eventId = event_id
                        await conn.enqueue(msg)
            except Exception as e:
                logger.warning("Catch-up replay error", exc_info=e)

    # 7. Connection TTL Task: close with code 4401 after 15 min (access token lifespan)
    async def connection_ttl_timer():
        try:
            await asyncio.sleep(15 * 60)
            if not conn.closed:
                conn.closed = True
                await websocket.close(code=4401, reason="token_expired")
        except asyncio.CancelledError:
            pass

    ttl_task = asyncio.create_task(connection_ttl_timer())

    # 8. Main receive loop
    try:
        while not conn.closed:
            data = await websocket.receive_text()
            await dispatch_message(conn, data, websocket.app.state)
    except WebSocketDisconnect:
        pass
    except Exception as e:
        logger.debug("WebSocket receive error", exc_info=e)
    finally:
        ttl_task.cancel()
        await manager.disconnect(conn_id)
        if presence_store:
            try:
                is_last = await presence_store.remove(user_id, conn_id)
                if is_last:
                    left_msg = UserLeftMessage(payload=UserLeftPayload(userId=user_id))
                    await manager.broadcast_ephemeral(left_msg)
            except Exception as e:
                logger.warning("Presence error on disconnect", exc_info=e)
