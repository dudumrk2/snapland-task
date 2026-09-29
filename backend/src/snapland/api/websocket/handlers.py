import orjson

from snapland.api.websocket.manager import Connection
from snapland.config import settings
from snapland.core.domain.area import CreateAreaRequest
from snapland.core.domain.ws_messages import (
    CursorMoveServerMessage,
    CursorMoveServerPayload,
    ErrorMessage,
    ErrorPayload,
    RemoteDrawMessage,
    RemoteDrawPayload,
    ServerMessage,
)
from snapland.core.interfaces.realtime import Envelope


async def dispatch_message(conn: Connection, raw_data: str, app_state) -> None:
    try:
        data = orjson.loads(raw_data)
        msg_type = data.get("type")
        payload = data.get("payload", {})
    except Exception:
        await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid JSON")))
        return

    rate_limiter = getattr(app_state, "rate_limiter", None)
    ephemeral_bus = getattr(app_state, "ephemeral_bus", None)

    # 1. Rate limiting checks per HLD §9.4
    if rate_limiter:
        if msg_type in ("DRAW_START", "DRAW_COMMIT", "DRAW_CANCEL"):
            res = await rate_limiter.check_limit(str(conn.user_id), "draw_action", 50, 60)
            if not res.allowed:
                await conn.enqueue(
                    ErrorMessage(payload=ErrorPayload(code="RATE_LIMITED", retryAfterMs=res.retry_after_ms))
                )
                return

        elif msg_type == "DRAW_UPDATE":
            res = await rate_limiter.check_limit(str(conn.user_id), "draw_stream", 900, 60)
            if not res.allowed:
                return

        elif msg_type == "CURSOR_MOVE":
            res = await rate_limiter.check_limit(str(conn.user_id), "cursor_throttle", 10, 1)
            if not res.allowed:
                return

    # 2. Dispatch by message type
    if not ephemeral_bus:
        return

    instance_id = settings.INSTANCE_ID
    out_msg: ServerMessage

    if msg_type == "CURSOR_MOVE":
        out_msg = CursorMoveServerMessage(
            payload=CursorMoveServerPayload(
                userId=conn.user_id,
                lat=payload["lat"],
                lng=payload["lng"]
            )
        )
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_START":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload.get("shapeId", ""),
                phase="start",
                append=[payload["point"]] if "point" in payload else []
            )
        )
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_UPDATE":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload.get("shapeId", ""),
                phase="update",
                seq=payload.get("seq"),
                fromIndex=payload.get("fromIndex"),
                append=payload.get("append")
            )
        )
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_COMMIT":
        shape_id = payload.get("shapeId", "")
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="commit",
                name=payload.get("name"),
                points=payload.get("points")
            )
        )
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

        area_service = getattr(app_state, "area_service", None)
        if area_service:
            req = CreateAreaRequest(
                name=payload.get("name", "Untitled Area"),
                coordinates=payload.get("points", []),
                shape_id=shape_id
            )
            try:
                await area_service.create_area(req, conn.user_id)
            except Exception as e:
                await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="INTERNAL_ERROR", message=str(e))))

    elif msg_type == "DRAW_CANCEL":
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=payload.get("shapeId", ""),
                phase="cancel"
            )
        )
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
