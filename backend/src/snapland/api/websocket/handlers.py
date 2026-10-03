import time
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
from snapland.middleware.metrics import ws_messages_dropped_total, ws_messages_total

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

    conn.last_received_time = time.monotonic()
    if msg_type in ("PING", "PONG"):
        return

    # Track inbound message metrics and structured log (type only, no coordinates or sensitive payloads)
    type_str = str(msg_type or "unknown")
    try:
        ws_messages_total.labels(type=type_str, direction="inbound").inc()
    except Exception:
        pass

    logger.info("WebSocket message received", type=type_str, conn_id=conn.conn_id, user_id=str(conn.user_id))

    rate_limiter = getattr(app_state, "rate_limiter", None)
    ephemeral_bus = getattr(app_state, "ephemeral_bus", None)
    manager = getattr(app_state, "ws_manager", None)

    # 1. Rate limiting checks per HLD §9.4
    if rate_limiter:
        if msg_type in ("DRAW_START", "DRAW_COMMIT", "DRAW_CANCEL"):
            try:
                res = await rate_limiter.check_limit(str(conn.user_id), "draw_action", 50, 60)
                if not res.allowed:
                    try:
                        ws_messages_dropped_total.labels(reason="rate_limited").inc()
                    except Exception:
                        pass
                    await conn.enqueue(
                        ErrorMessage(payload=ErrorPayload(code="RATE_LIMITED", retryAfterMs=res.retry_after_ms))
                    )
                    return
            except Exception as e:
                logger.warning("Rate limiter error for draw_action", conn_id=conn.conn_id, error=str(e))

        elif msg_type == "DRAW_UPDATE":
            try:
                res = await rate_limiter.check_limit(str(conn.user_id), "draw_stream", 900, 60)
                if not res.allowed:
                    try:
                        ws_messages_dropped_total.labels(reason="rate_limited").inc()
                    except Exception:
                        pass
                    now = time.monotonic()
                    if now - conn.last_draw_stream_rate_limit_error >= 10.0:
                        conn.last_draw_stream_rate_limit_error = now
                        await conn.enqueue(
                            ErrorMessage(
                                payload=ErrorPayload(
                                    code="RATE_LIMITED",
                                    message="Draw stream rate limit exceeded",
                                    retryAfterMs=res.retry_after_ms,
                                )
                            )
                        )
                    return
            except Exception as e:
                logger.warning("Rate limiter error for draw_stream", conn_id=conn.conn_id, error=str(e))

    # 2. Dispatch by message type
    instance_id = settings.INSTANCE_ID
    out_msg: ServerMessage

    if msg_type == "CURSOR_MOVE":
        now = time.monotonic()
        # In-process per-connection throttle: 1 per 100 ms (10 Hz)
        if now - conn.last_cursor_time < 0.1:
            try:
                ws_messages_dropped_total.labels(reason="throttled").inc()
            except Exception:
                pass
            return
        conn.last_cursor_time = now

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
                lng=lng_f,
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        if ephemeral_bus:
            try:
                await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
            except Exception as e:
                logger.warning("Ephemeral publish failed for CURSOR_MOVE", conn_id=conn.conn_id, error=str(e))

    elif msg_type == "DRAW_START":
        shape_id = str(payload.get("shapeId", ""))[:64]
        if not shape_id:
            return
        append_coords: list[Coordinate] = []
        if "point" in payload:
            valid_pt = _validate_coordinate(payload["point"])
            if valid_pt:
                append_coords.append(valid_pt)
        elif "append" in payload and isinstance(payload["append"], list):
            for pt in payload["append"]:
                valid_pt = _validate_coordinate(pt)
                if valid_pt:
                    append_coords.append(valid_pt)

        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="start",
                append=append_coords,
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        if ephemeral_bus:
            try:
                await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
            except Exception as e:
                logger.warning("Ephemeral publish failed for DRAW_START", conn_id=conn.conn_id, error=str(e))

    elif msg_type == "DRAW_UPDATE":
        shape_id = str(payload.get("shapeId", ""))[:64]
        if not shape_id:
            return

        raw_seq = payload.get("seq")
        raw_from_index = payload.get("fromIndex")
        seq_val: Optional[int] = None
        from_index_val: Optional[int] = None
        if raw_seq is not None:
            try:
                seq_val = int(raw_seq)
            except (ValueError, TypeError):
                await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid seq")))
                return
        if raw_from_index is not None:
            try:
                from_index_val = int(raw_from_index)
            except (ValueError, TypeError):
                await conn.enqueue(ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message="Invalid fromIndex")))
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
                seq=seq_val,
                fromIndex=from_index_val,
                append=append_coords,
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        if ephemeral_bus:
            try:
                await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
            except Exception as e:
                logger.warning("Ephemeral publish failed for DRAW_UPDATE", conn_id=conn.conn_id, error=str(e))

    elif msg_type == "DRAW_COMMIT":
        shape_id = str(payload.get("shapeId", ""))[:64]
        commit_shape_id: Optional[str] = shape_id if shape_id else None
        raw_name = payload.get("name")
        name = str(raw_name).strip()[:100] if raw_name else "Untitled Area"
        if not name:
            name = "Untitled Area"

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
            req = CreateAreaRequest(name=name, coordinates=points, shape_id=commit_shape_id)
            if hasattr(app_state, "area_service") and app_state.area_service:
                await app_state.area_service.create_area(req, conn.user_id)
            elif hasattr(app_state, "session_factory") and app_state.session_factory:
                from snapland.api.deps import build_area_service

                async with app_state.session_factory() as session:
                    svc = build_area_service(session, app_state)
                    await svc.create_area(req, conn.user_id)
            else:
                logger.error("No area_service or session_factory available")
                await conn.enqueue(
                    ErrorMessage(payload=ErrorPayload(code="INTERNAL_ERROR", message="Service unavailable"))
                )
                return
        except (ValidationError, PydanticValidationError) as e:
            reason = getattr(e, "reason", "Invalid polygon geometry")
            await conn.enqueue(
                ErrorMessage(payload=ErrorPayload(code="VALIDATION_ERROR", message=f"Invalid polygon: {reason}"))
            )
            return
        except Exception as e:
            logger.error("Failed to save area from DRAW_COMMIT", conn_id=conn.conn_id, error=str(e))
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
                points=points,
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        if ephemeral_bus:
            try:
                await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
            except Exception as e:
                logger.warning("Ephemeral publish failed for DRAW_COMMIT", conn_id=conn.conn_id, error=str(e))

    elif msg_type == "DRAW_CANCEL":
        shape_id = str(payload.get("shapeId", ""))[:64]
        out_msg = RemoteDrawMessage(
            payload=RemoteDrawPayload(
                userId=conn.user_id,
                shapeId=shape_id,
                phase="cancel",
            )
        )
        if manager:
            await manager.broadcast_ephemeral(out_msg, exclude_conn_id=conn.conn_id)
        if ephemeral_bus:
            try:
                await ephemeral_bus.publish(Envelope(origin=instance_id, message=out_msg))
            except Exception as e:
                logger.warning("Ephemeral publish failed for DRAW_CANCEL", conn_id=conn.conn_id, error=str(e))
