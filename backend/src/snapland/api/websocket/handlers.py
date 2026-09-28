import orjson
from uuid import UUID

from snapland.core.domain.ws_messages import (
    ErrorMessage, ErrorPayload,
    CursorMoveServerMessage, CursorMoveServerPayload,
    RemoteDrawMessage, RemoteDrawPayload
)
from snapland.api.websocket.manager import Connection
from snapland.core.interfaces.realtime import Envelope
from snapland.core.domain.area import CreateAreaRequest

async def dispatch_message(conn: Connection, raw_data: str, app_state):
    try:
        data = orjson.loads(raw_data)
        msg_type = data.get("type")
        payload = data.get("payload")
    except Exception:
        await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid JSON")))
        return
        
    rate_limiter = app_state.rate_limiter
    ephemeral_bus = app_state.ephemeral_bus
    
    if msg_type in ("DRAW_START", "DRAW_COMMIT", "DRAW_CANCEL"):
        res = await rate_limiter.check_limit(str(conn.user_id), "draw_action", 50, 60)
        if not res.allowed:
            await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="RATE_LIMITED", retryAfterMs=res.retry_after_ms)))
            return
            
    elif msg_type == "DRAW_UPDATE":
        res = await rate_limiter.check_limit(str(conn.user_id), "draw_stream", 900, 60)
        if not res.allowed:
            return 
            
    elif msg_type == "CURSOR_MOVE":
        res = await rate_limiter.check_limit(str(conn.user_id), "cursor_throttle", 10, 1)
        if not res.allowed:
            return
            
    if msg_type == "CURSOR_MOVE":
        out_msg = CursorMoveServerMessage(
            payload=CursorMoveServerPayload(
                userId=conn.user_id,
                lat=payload["lat"],
                lng=payload["lng"]
            )
        )
        await ephemeral_bus.publish(Envelope(origin=app_state.config.INSTANCE_ID, message=out_msg))
        
    elif msg_type == "DRAW_UPDATE":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload["shapeId"],
                phase="update",
                seq=payload["seq"],
                fromIndex=payload["fromIndex"],
                append=payload["append"]
            )
        )
        await ephemeral_bus.publish(Envelope(origin=app_state.config.INSTANCE_ID, message=out_msg))

    elif msg_type == "DRAW_START":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload["shapeId"],
                phase="start",
                append=[payload["point"]]
            )
        )
        await ephemeral_bus.publish(Envelope(origin=app_state.config.INSTANCE_ID, message=out_msg))

    elif msg_type == "DRAW_COMMIT":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload["shapeId"],
                phase="commit",
                name=payload["name"],
                points=payload["points"]
            )
        )
        await ephemeral_bus.publish(Envelope(origin=app_state.config.INSTANCE_ID, message=out_msg))
        
        area_service = app_state.area_service
        req = CreateAreaRequest(name=payload["name"], coordinates=payload["points"])
        try:
            await area_service.create_area(req, conn.user_id)
        except Exception as e:
            await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="INTERNAL_ERROR", message=str(e))))

    elif msg_type == "DRAW_CANCEL":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload["shapeId"],
                phase="cancel"
            )
        )
        await ephemeral_bus.publish(Envelope(origin=app_state.config.INSTANCE_ID, message=out_msg))
