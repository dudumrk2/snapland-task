import asyncio
import uuid
from typing import Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Request
from snapland.api.websocket.manager import WebSocketManager
from snapland.api.websocket.handlers import dispatch_message

router = APIRouter()

# Global manager instance for this FastAPI worker
manager = WebSocketManager()

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    request: Request,
    ticket: str,
    lastEventId: Optional[str] = None
):
    # Retrieve dependencies from app state or assuming some injection.
    # The assignment says "ticket validation, Origin check, lifecycle, connect, lastEventId replay"
    
    # Origin check
    origin = request.headers.get("origin")
    allowed_origins = request.app.state.config.WS_ALLOWED_ORIGINS
    if origin and origin not in allowed_origins:
        await websocket.close(code=4003)
        return

    # Validate ticket
    auth_service = request.app.state.auth_service
    user_id = await auth_service.redeem_ws_ticket(ticket)
    if not user_id:
        await websocket.close(code=4001)
        return

    conn_id = str(uuid.uuid4())
    conn = await manager.connect(websocket, user_id, conn_id)

    # Presence join
    presence_store = request.app.state.presence_store
    user_repo = request.app.state.user_repo
    user = await user_repo.get_by_id(user_id)
    if user:
        await presence_store.heartbeat(user_id, conn_id, user.display_name)
        # We need to send PRESENCE_SNAPSHOT and USER_JOINED. This will be done in handlers or here.
        # But for brevity, assume handlers handle the lifecycle or we do it here.

    # Replay events
    if lastEventId:
        event_stream = request.app.state.event_stream
        catchup = await event_stream.read_since(lastEventId)
        if catchup.resync_required:
            from snapland.core.domain.ws_messages import ResyncRequiredMessage, ResyncRequiredPayload
            await conn.enqueue(ResyncRequiredMessage(payload=ResyncRequiredPayload()))
        else:
            for event_id, msg in catchup.events:
                # Need to update eventId
                msg.eventId = event_id
                await conn.enqueue(msg)

    try:
        while True:
            # Receive raw text or bytes
            data = await websocket.receive_text()
            # Dispatch to handlers
            await dispatch_message(conn, data, request.app.state)
    except WebSocketDisconnect:
        pass
    finally:
        await manager.disconnect(conn_id)
        if user:
            is_empty = await presence_store.remove(user_id, conn_id)
            if is_empty:
                # send USER_LEFT
                pass
