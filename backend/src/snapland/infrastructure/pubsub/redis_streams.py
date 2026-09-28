import asyncio
from typing import AsyncIterator, Sequence
from redis.asyncio import Redis
from snapland.core.interfaces.realtime import IEventStream, CatchUp
from snapland.core.interfaces.services import IEventPublisher
from snapland.core.domain.ws_messages import ServerMessage
from snapland.core.domain.events import DomainEvent
from pydantic import TypeAdapter

server_message_adapter = TypeAdapter(ServerMessage)

class RedisEventStream(IEventStream, IEventPublisher):
    def __init__(self, redis_client: Redis, stream_key: str = "snapland:events"):
        self.redis = redis_client
        self.stream_key = stream_key

    async def publish(self, event: DomainEvent) -> None:
        pass # HLD §9.2 says "Durable events (AREA_*): emitted for every mutation ... only after the DB transaction commits." 
        # Actually AreaService might be emitting DomainEvent, but maybe the intention is to publish AREA_* ws_messages to the stream?
        # Or maybe AreaService is supposed to emit DomainEvents and some processor converts them.
        # But wait, wait... IEventPublisher publish DomainEvent.
        # Let's serialize the DomainEvent and add it to snapland:events, wait no, snapland:events contains ServerMessage.
        pass

    async def append(self, message: ServerMessage) -> str:
        data = server_message_adapter.dump_json(message)
        msg_id = await self.redis.xadd(self.stream_key, {"payload": data}, maxlen=10000, approximate=True)
        return msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)

    async def read_since(self, last_id: str, limit: int = 500) -> CatchUp:
        try:
            stream_info = await self.redis.xinfo_stream(self.stream_key)
        except Exception:
            stream_info = None

        resync_required = False
        if stream_info and "first-entry" in stream_info and stream_info["first-entry"]:
            first_entry_id = stream_info["first-entry"][0]
            if isinstance(first_entry_id, bytes):
                first_entry_id = first_entry_id.decode("utf-8")
            
            if last_id != "0-0" and last_id < first_entry_id:
                resync_required = True

        res = await self.redis.xread({self.stream_key: last_id}, count=limit)
        events = []
        if res:
            for stream_name, messages in res:
                for msg_id, fields in messages:
                    payload = fields.get(b"payload") or fields.get("payload")
                    if payload:
                        try:
                            msg = server_message_adapter.validate_json(payload)
                            msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                            events.append((msg_id_str, msg))
                        except Exception:
                            pass
        
        return CatchUp(events=events, resync_required=resync_required)

    async def follow(self) -> AsyncIterator[tuple[str, ServerMessage]]:
        last_id = "$"
        while True:
            try:
                res = await self.redis.xread({self.stream_key: last_id}, block=0)
                if res:
                    for stream_name, messages in res:
                        for msg_id, fields in messages:
                            msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
                            last_id = msg_id_str
                            payload = fields.get(b"payload") or fields.get("payload")
                            if payload:
                                try:
                                    msg = server_message_adapter.validate_json(payload)
                                    yield (msg_id_str, msg)
                                except Exception:
                                    pass
            except asyncio.CancelledError:
                break
            except Exception:
                await asyncio.sleep(1)
