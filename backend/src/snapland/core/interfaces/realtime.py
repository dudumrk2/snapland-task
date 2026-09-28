from dataclasses import dataclass
from typing import AsyncIterator, Protocol, Sequence
from uuid import UUID
from snapland.core.domain.ws_messages import ServerMessage, PresenceUser

@dataclass(frozen=True)
class Envelope:
    origin: str                # INSTANCE_ID of the publishing instance (receivers skip their own)
    message: ServerMessage

@dataclass(frozen=True)
class CatchUp:
    events: Sequence[tuple[str, ServerMessage]]   # (stream id, AREA_* message)
    resync_required: bool                     # last_id older than retention ⇒ client must refetch over HTTP

class IEphemeralBus(Protocol):                # Redis Pub/Sub — loss-tolerant
    async def publish(self, envelope: Envelope) -> None: ...
    def subscribe(self) -> AsyncIterator[Envelope]: ...

class IEventStream(Protocol):                 # Redis Streams — durable, replayable
    async def append(self, message: ServerMessage) -> str: ...                       # returns stream id (eventId)
    async def read_since(self, last_id: str, limit: int = 500) -> CatchUp: ...
    def follow(self) -> AsyncIterator[tuple[str, ServerMessage]]: ...                # XREAD BLOCK from "$"

class IPresenceStore(Protocol):               # Redis ZSET, heartbeat-based
    async def heartbeat(self, user_id: UUID, conn_id: str, display_name: str) -> None: ...
    async def remove(self, user_id: UUID, conn_id: str) -> bool: ...             # True ⇒ user has no connections left
    async def snapshot(self) -> Sequence[PresenceUser]: ...
    async def reap_expired(self) -> Sequence[UUID]: ...                          # crash recovery: users to announce as left
