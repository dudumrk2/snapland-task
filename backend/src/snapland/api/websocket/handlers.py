import logging

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
        lat = payload.get("lat")
        lng = payload.get("lng")
        if lat is None or lng is None:
            return
        try:
            lat_f = float(lat)
            lng_f = float(lng)
        except (ValueError, TypeError):
            return
        out_msg = CursorMoveServerMessage(
            payload=CursorMoveServerPayload(
                userId=conn.user_id,
                lat=lat_f,
                lng=lng_f
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
        elif hasattr(app_state, "session_factory") and app_state.session_factory:
            from snapland.core.services.area_service import AreaService
            from snapland.core.services.audit_service import AuditService
            from snapland.core.services.spatial_service import SpatialService
            from snapland.infrastructure.cache.cache_repository import CacheRepository
            from snapland.infrastructure.db.repositories.area_repository import AreaRepository
            from snapland.infrastructure.pubsub.redis_streams import RedisEventStream

            try:
                async with app_state.session_factory() as session:
                    area_repo = AreaRepository(session)
                    spatial_svc = SpatialService()
                    audit_svc = AuditService()
                    cache_repo = getattr(app_state, "cache_repo", None)
                    if not cache_repo and hasattr(app_state, "redis"):
                        cache_repo = CacheRepository(app_state.redis)
                    event_publisher = getattr(app_state, "event_stream", None)
                    if not event_publisher and hasattr(app_state, "redis"):
                        event_publisher = RedisEventStream(app_state.redis)
                    if cache_repo and event_publisher:
                        svc = AreaService(
                            repo=area_repo,
                            spatial=spatial_svc,
                            cache=cache_repo,
                            events=event_publisher,
                            audit=audit_svc
                        )
                        req = CreateAreaRequest(
                            name=payload.get("name", "Untitled Area"),
                            coordinates=payload.get("points", []),
                            shape_id=shape_id
                        )
                        await svc.create_area(req, conn.user_id)
                        await session.commit()
            except Exception as e:
                logging.getLogger(__name__).error("Error creating area from DRAW_COMMIT: %s", e, exc_info=e)
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
