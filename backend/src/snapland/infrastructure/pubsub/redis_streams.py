import asyncio
import re
import time
from typing import Any, AsyncIterator

from pydantic import TypeAdapter
from redis.asyncio import Redis

from snapland.core.domain.events import AreaCreated, AreaDeleted, AreaUpdated, DomainEvent
from snapland.core.domain.ws_messages import (
    AreaDeletedMessage,
    AreaDeletedPayload,
    AreaSavedMessage,
    AreaSavedPayload,
    AreaUpdatedMessage,
    AreaUpdatedPayload,
    ServerMessage,
)
from snapland.core.interfaces.realtime import CatchUp, IEventStream
from snapland.core.interfaces.services import IEventPublisher

server_message_adapter: TypeAdapter[ServerMessage] = TypeAdapter(ServerMessage)


def parse_stream_id(id_str: str) -> tuple[int, int]:
    try:
        parts = id_str.split("-")
        return (int(parts[0]), int(parts[1]))
    except Exception:
        return (0, 0)


class RedisEventStream(IEventStream, IEventPublisher):
    def __init__(self, redis_client: Redis, stream_key: str = "snapland:events"):
        self.redis = redis_client
        self.stream_key = stream_key

    async def publish(self, event: DomainEvent) -> None:
        """Emits durable events (AREA_*) to persistent Redis Stream."""
        msg: ServerMessage
        if isinstance(event, AreaCreated):
            if event.area:
                msg = AreaSavedMessage(
                    eventId="",
                    payload=AreaSavedPayload(area=event.area, shapeId=event.shape_id)
                )
                await self.append(msg)
        elif isinstance(event, AreaUpdated):
            if event.area:
                msg = AreaUpdatedMessage(
                    eventId="",
                    payload=AreaUpdatedPayload(area=event.area)
                )
                await self.append(msg)
        elif isinstance(event, AreaDeleted):
            msg = AreaDeletedMessage(
                eventId="",
                payload=AreaDeletedPayload(areaId=event.area_id)
            )
            await self.append(msg)

    async def append(self, message: ServerMessage) -> str:
        data = server_message_adapter.dump_json(message).decode("utf-8")
        min_timestamp = int((time.time() - 300) * 1000)
        msg_id = await self.redis.xadd(
            self.stream_key,
            {"payload": data},
            minid=f"{min_timestamp}-0",
            approximate=True
        )
        await self.redis.xtrim(self.stream_key, maxlen=10000, approximate=True)
        return msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

    async def read_since(self, last_id: str, limit: int = 150) -> CatchUp:
        # Validate last_id format
        if not last_id or not re.match(r"^\d+-\d+$", last_id):
            return CatchUp(events=[], resync_required=True)

        try:
            stream_info = await self.redis.xinfo_stream(self.stream_key)
        except Exception:
            stream_info = None

        if last_id != "0-0" and stream_info and "first-entry" in stream_info and stream_info["first-entry"]:
            first_entry_id = stream_info["first-entry"][0]
            if isinstance(first_entry_id, bytes):
                first_entry_id = first_entry_id.decode("utf-8")

            if parse_stream_id(last_id) < parse_stream_id(first_entry_id):
                return CatchUp(events=[], resync_required=True)

        raw_res: Any = await self.redis.xread({self.stream_key: last_id}, count=limit + 1)
        events: list[tuple[str, ServerMessage]] = []
        if raw_res and isinstance(raw_res, list):
            for stream_item in raw_res:
                messages = stream_item[1] if isinstance(stream_item, (list, tuple)) and len(stream_item) > 1 else []
                for msg_entry in messages:
                    if not isinstance(msg_entry, (list, tuple)) or len(msg_entry) < 2:
                        continue
                    msg_id, fields = msg_entry[0], msg_entry[1]
                    if not isinstance(fields, dict):
                        continue
                    payload = fields.get(b"payload") or fields.get("payload")
                    if payload:
                        try:
                            msg = server_message_adapter.validate_json(payload)
                            msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                            if hasattr(msg, "eventId"):
                                msg.eventId = msg_id_str
                            events.append((msg_id_str, msg))
                        except Exception:
                            pass

        if len(events) > limit:
            return CatchUp(events=[], resync_required=True)

        return CatchUp(events=events, resync_required=False)

    async def follow(self) -> AsyncIterator[tuple[str, ServerMessage]]:
        last_id = "$"
        while True:
            try:
                raw_res: Any = await self.redis.xread({self.stream_key: last_id}, block=1000)
                if not raw_res:
                    await asyncio.sleep(0.05)
                    continue
                if isinstance(raw_res, list):
                    for stream_item in raw_res:
                        messages = stream_item[1] if isinstance(stream_item, (list, tuple)) and len(stream_item) > 1 else []
                        for msg_entry in messages:
                            if not isinstance(msg_entry, (list, tuple)) or len(msg_entry) < 2:
                                continue
                            msg_id, fields = msg_entry[0], msg_entry[1]
                            if not isinstance(fields, dict):
                                continue
                            msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                            last_id = msg_id_str
                            payload = fields.get(b"payload") or fields.get("payload")
                            if payload:
                                try:
                                    msg = server_message_adapter.validate_json(payload)
                                    if hasattr(msg, "eventId"):
                                        msg.eventId = msg_id_str
                                    yield (msg_id_str, msg)
                                except Exception:
                                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(0.5)
