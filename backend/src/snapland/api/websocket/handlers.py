from typing import Any, Optional

import orjson
import structlog
from pydantic import ValidationError as PydanticValidationError

from snapland.api.websocket.manager import Connection
from snapland.config import settings
from snapland.core.domain.area import Coordinate, CreateAreaRequest
from snapland.core.domain.exceptions import ValidationError
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

logger = structlog.get_logger(__name__)


def _validate_coordinate(coord: Any) -> Optional[Coordinate]:
    if not isinstance(coord, dict):
        return None
    lat = coord.get("lat")
    lng = coord.get("lng")
    if lat is None or lng is None:
        return None
    try:
        lat_f = float(lat)
        lng_f = float(lng)
        if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
            return None
        return Coordinate(lat=lat_f, lng=lng_f)
    except (ValueError, TypeError):
        return None


async def dispatch_message(conn: Connection, raw_data: str, app_state: Any) -> None:
    try:
        data = orjson.loads(raw_data)
        if not isinstance(data, dict):
            await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid payload")))
            return
        msg_type = data.get("type")
        payload = data.get("payload")
        if not isinstance(payload, dict):
            payload = {}
    except Exception:
        await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid JSON")))
        return

    rate_limiter = getattr(app_state, "rate_limiter", None)
    ephemeral_bus = getattr(app_state, "ephemeral_bus", None)
    manager = getattr(app_state, "ws_manager", None)

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
        lat = payload.get("lat")
        lng = payload.get("lng")
        if lat is None or lng is None:
            return
        try:
            lat_f = float(lat)
            lng_f = float(lng)
            if not (-90.0 <= lat_f <= 90.0 and -180.0 <= lng_f <= 180.0):
                return
        except (ValueError, TypeError):
            return

        out_msg = CursorMoveServerMessage(
            payload=CursorMoveServerPayload(
                userId=conn.user_id,
                lat=lat_f,
                lng=lng_f
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_START":
        shape_id = str(payload.get("shapeId", ""))[:64]
        if not shape_id:
            return
        append_coords: list[Coordinate] = []
        if "point" in payload:
            valid_pt = _validate_coordinate(payload["point"])
            if valid_pt:
                append_coords.append(valid_pt)

        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="start",
                append=append_coords
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_UPDATE":
        shape_id = str(payload.get("shapeId", ""))[:64]
        if not shape_id:
            return

        raw_append = payload.get("append", [])
        if not isinstance(raw_append, list) or len(raw_append) > 1000:
            return

        append_coords = []
        for pt in raw_append:
            valid_pt = _validate_coordinate(pt)
            if valid_pt:
                append_coords.append(valid_pt)

        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="update",
                seq=payload.get("seq"),
                fromIndex=payload.get("fromIndex"),
                append=append_coords
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_COMMIT":
        shape_id = str(payload.get("shapeId", ""))[:64]
        name = str(payload.get("name", "Untitled Area"))[:100]
        raw_points = payload.get("points", [])

        if not isinstance(raw_points, list) or len(raw_points) < 3 or len(raw_points) > 1000:
            await conn.enqueue(
                ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid polygon coordinates"))
            )
            return

        points: list[Coordinate] = []
        for pt in raw_points:
            valid_pt = _validate_coordinate(pt)
            if not valid_pt:
                await conn.enqueue(
                    ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid coordinate values"))
                )
                return
            points.append(valid_pt)

        try:
            req = CreateAreaRequest(name=name, coordinates=points, shape_id=shape_id)
            if hasattr(app_state, "area_service") and app_state.area_service:
                await app_state.area_service.create_area(req, conn.user_id)
            elif hasattr(app_state, "session_factory") and app_state.session_factory:
                from snapland.api.deps import build_area_service
                async with app_state.session_factory() as session:
                    svc = build_area_service(session, app_state)
                    await svc.create_area(req, conn.user_id)
                    await session.commit()
            else:
                logger.error("No area_service or session_factory available")
                await conn.enqueue(
                    ErrorMessage(payload=ErrorPayload(code="INTERNAL_ERROR", message="Service unavailable"))
                )
                return
        except (ValidationError, PydanticValidationError) as e:
            await conn.enqueue(
                ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message=f"Invalid polygon: {e}"))
            )
            return
        except Exception as e:
            logger.error("Failed to save area from DRAW_COMMIT", error=str(e))
            await conn.enqueue(
                ErrorMessage(payload=ErrorPayload(code="INTERNAL_ERROR", message="Failed to save area"))
            )
            return

        # Peer notification only broadcast AFTER successful commit
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="commit",
                name=name,
                points=points
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))

    elif msg_type == "DRAW_CANCEL":
        shape_id = str(payload.get("shapeId", ""))[:64]
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="cancel"
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
