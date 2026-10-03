import asyncio
import collections
import time
from typing import Any, Dict, Optional
from uuid import UUID

import orjson
import structlog
from fastapi import WebSocket

from snapland.core.domain.user import User
from snapland.core.domain.ws_messages import RemoteDrawMessage, ServerMessage
from snapland.middleware.metrics import (
    ws_connections_active,
    ws_messages_dropped_total,
    ws_messages_total,
    ws_outbound_queue_depth,
)

logger = structlog.get_logger(__name__)

DURABLE_TYPES = frozenset({"AREA_SAVED", "AREA_UPDATED", "AREA_DELETED"})
# Messages that must never be evicted from the queue — dropping them would leave the
# client silently stale (RESYNC_REQUIRED) or never getting an error feedback.
PROTECTED_TYPES = frozenset({"RESYNC_REQUIRED", "PRESENCE_SNAPSHOT", "ERROR", "PING", "PONG"})

# Maintain module-level alias for backwards compatibility with tests
WS_MESSAGES_DROPPED_TOTAL = ws_messages_dropped_total


class ConnectionQueue:
    def __init__(self, maxsize: int = 256):
        self.maxsize = maxsize
        self._items: collections.deque[ServerMessage] = collections.deque()
        self._has_items = asyncio.Event()
        self._loop: Optional[asyncio.AbstractEventLoop] = None

    def qsize(self) -> int:
        return len(self._items)

    def empty(self) -> bool:
        return len(self._items) == 0

    def full(self) -> bool:
        return len(self._items) >= self.maxsize

    async def get(self) -> ServerMessage:
        if self._loop is None:
            self._loop = asyncio.get_running_loop()
        while not self._items:
            self._has_items.clear()
            await self._has_items.wait()
        item = self._items.popleft()
        if not self._items:
            self._has_items.clear()
        return item

    def get_nowait(self) -> ServerMessage:
        if not self._items:
            raise asyncio.QueueEmpty()
        item = self._items.popleft()
        if not self._items:
            self._has_items.clear()
        return item

    def push(self, message: ServerMessage) -> None:
        self._items.append(message)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._has_items.set)
        else:
            self._has_items.set()

    def push_front(self, message: ServerMessage) -> None:
        self._items.appendleft(message)
        if self._loop is not None and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._has_items.set)
        else:
            self._has_items.set()

    def evict_oldest_ephemeral(self) -> bool:
        """Finds and evicts the oldest ephemeral, non-protected message. Returns True if evicted, False if none found."""
        for idx, item in enumerate(self._items):
            if item.type not in DURABLE_TYPES and item.type not in PROTECTED_TYPES:
                del self._items[idx]
                if not self._items:
                    self._has_items.clear()
                return True
        return False


class Connection:
    def __init__(self, websocket: WebSocket, user_id: UUID, conn_id: str, maxsize: int = 256):
        self.websocket = websocket
        self.user_id = user_id
        self.conn_id = conn_id
        self.queue = ConnectionQueue(maxsize=maxsize)
        self.writer_task: Optional[asyncio.Task] = None
        self.closed = False
        self.dropped_count = 0
        self.user: Optional[User] = None
        self.last_cursor_time: float = 0.0
        self.last_draw_stream_rate_limit_error: float = 0.0
        self.last_received_time: float = time.monotonic()
        self.last_ping_time: Optional[float] = None
        self.last_pong_time: float = time.monotonic()
        self.seen_event_ids: collections.deque[str] = collections.deque(maxlen=500)
        self._close_tasks: set[asyncio.Task[Any]] = set()

    async def enqueue(self, message: ServerMessage) -> None:
        if self.closed:
            return

        if hasattr(message, "eventId") and message.eventId:
            if message.eventId in self.seen_event_ids:
                return
            self.seen_event_ids.append(message.eventId)

        is_durable = message.type in DURABLE_TYPES

        try:
            ws_outbound_queue_depth.observe(self.queue.qsize())
        except Exception:
            pass

        if self.queue.full():
            evicted = self.queue.evict_oldest_ephemeral()
            if evicted:
                self.dropped_count += 1
                try:
                    ws_messages_dropped_total.labels(reason="queue_full").inc()
                except Exception:
                    pass
            else:
                # Queue has only durables or protected messages
                if is_durable or message.type in PROTECTED_TYPES:
                    self.closed = True
                    close_task = asyncio.create_task(self.websocket.close(code=1013))
                    self._close_tasks.add(close_task)
                    close_task.add_done_callback(self._close_tasks.discard)
                    return
                else:
                    # Drop incoming ephemeral message without closing socket
                    self.dropped_count += 1
                    try:
                        ws_messages_dropped_total.labels(reason="queue_full").inc()
                    except Exception:
                        pass
                    return

        self.queue.push(message)


class WebSocketManager:
    MAX_CONNECTIONS_PER_USER = 5

    def __init__(self):
        self.all_connections: Dict[str, Connection] = {}
        self.active_connections: Dict[str, Connection] = {}

    @property
    def total_dropped_count(self) -> int:
        return sum(c.dropped_count for c in self.all_connections.values())

    async def connect(
        self, websocket: WebSocket, user_id: UUID, conn_id: str, register: bool = True
    ) -> Optional[Connection]:
        user_conns = self.get_user_connections(user_id)
        if len(user_conns) >= self.MAX_CONNECTIONS_PER_USER:
            await websocket.accept()
            await websocket.close(code=4003, reason="too_many_connections")
            return None

        await websocket.accept()
        conn = Connection(websocket, user_id, conn_id)
        self.all_connections[conn_id] = conn
        conn.writer_task = asyncio.create_task(self._writer(conn))
        if register:
            self.active_connections[conn_id] = conn

        try:
            ws_connections_active.inc()
        except Exception:
            pass

        return conn

    def register(self, conn: Connection) -> None:
        if not conn.closed:
            self.active_connections[conn.conn_id] = conn

    async def disconnect(self, conn_id: str):
        conn = self.all_connections.pop(conn_id, None)
        self.active_connections.pop(conn_id, None)
        if conn:
            try:
                ws_connections_active.dec()
            except Exception:
                pass
            conn.closed = True
            if conn.writer_task:
                conn.writer_task.cancel()
                try:
                    await conn.writer_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.debug("Writer task error on disconnect", exc_info=e)

    async def disconnect_user(self, user_id: UUID):
        for conn in list(self.all_connections.values()):
            if conn.user_id == user_id:
                try:
                    await conn.websocket.close(code=4401, reason="logged_out")
                except Exception:
                    pass
                await self.disconnect(conn.conn_id)

    async def _writer(self, conn: Connection):
        PING_INTERVAL = 30.0  # send keep-alive ping every 30s
        PONG_TIMEOUT = 10.0   # close if no pong within 10s

        next_ping_time = time.monotonic() + PING_INTERVAL

        try:
            while not conn.closed:
                now = time.monotonic()

                # Check if waiting for pong has exceeded timeout
                if conn.last_ping_time is not None:
                    if now - conn.last_ping_time > PONG_TIMEOUT:
                        logger.info("WebSocket keepalive pong timeout, closing connection", conn_id=conn.conn_id)
                        conn.closed = True
                        try:
                            await conn.websocket.close(code=1001, reason="pong_timeout")
                        except Exception:
                            pass
                        return
                    wait_timeout = max(0.01, PONG_TIMEOUT - (now - conn.last_ping_time))
                else:
                    wait_timeout = max(0.01, next_ping_time - now)

                try:
                    msg = await asyncio.wait_for(conn.queue.get(), timeout=wait_timeout)
                except asyncio.TimeoutError:
                    now = time.monotonic()
                    if conn.last_ping_time is not None:
                        logger.info("WebSocket keepalive pong timeout, closing connection", conn_id=conn.conn_id)
                        conn.closed = True
                        try:
                            await conn.websocket.close(code=1001, reason="pong_timeout")
                        except Exception:
                            pass
                        return
                    else:
                        # Time to send PING frame
                        conn.last_ping_time = now
                        next_ping_time = now + PING_INTERVAL
                        try:
                            await conn.websocket.send_text(orjson.dumps([{"type": "PING"}]).decode("utf-8"))
                        except Exception:
                            conn.closed = True
                            return
                        continue

                batch = [msg]

                # If time to ping coincides with outbound data batch, include PING frame
                now = time.monotonic()
                if conn.last_ping_time is None and now >= next_ping_time:
                    conn.last_ping_time = now
                    next_ping_time = now + PING_INTERVAL
                    from snapland.core.domain.ws_messages import PingMessage
                    batch.append(PingMessage())

                is_durable = msg.type in DURABLE_TYPES
                if not is_durable:
                    deadline = asyncio.get_running_loop().time() + 0.05
                    while True:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            break
                        try:
                            m = await asyncio.wait_for(conn.queue.get(), timeout=remaining)
                            batch.append(m)
                            if m.type in DURABLE_TYPES:
                                break
                        except asyncio.TimeoutError:
                            break
                else:
                    while not conn.queue.empty():
                        m = conn.queue.get_nowait()
                        batch.append(m)

                coalesced = self._coalesce(batch)
                data = [m.model_dump(by_alias=True, exclude_none=True) for m in coalesced]

                for m in coalesced:
                    try:
                        ws_messages_total.labels(type=m.type, direction="outbound").inc()
                    except Exception:
                        pass

                await conn.websocket.send_text(orjson.dumps(data).decode("utf-8"))

        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("WebSocket writer error", conn_id=conn.conn_id, error=str(e))
            conn.closed = True
            try:
                await conn.websocket.close()
            except Exception:
                pass

    def _coalesce(self, batch: list[ServerMessage]) -> list[ServerMessage]:
        result: list[ServerMessage] = []
        cursor_indices: dict[UUID, int] = {}
        pending_draw_indices: dict[tuple[UUID, str], int] = {}

        for msg in batch:
            if msg.type == "CURSOR_MOVE":
                user_id = msg.payload.userId
                if user_id in cursor_indices:
                    idx = cursor_indices[user_id]
                    result[idx] = msg.model_copy(deep=True)
                else:
                    cursor_indices[user_id] = len(result)
                    result.append(msg.model_copy(deep=True))

            elif msg.type == "REMOTE_DRAW":
                draw_key = (msg.payload.userId, msg.payload.shapeId)
                if msg.payload.phase == "update" and draw_key in pending_draw_indices:
                    idx = pending_draw_indices[draw_key]
                    prev = result[idx]
                    if (
                        isinstance(prev, RemoteDrawMessage)
                        and prev.payload.seq is not None
                        and msg.payload.seq is not None
                        and prev.payload.seq + 1 == msg.payload.seq
                    ):
                        prev_append = list(prev.payload.append or [])
                        new_append = list(msg.payload.append or [])
                        result[idx] = prev.model_copy(
                            update={
                                "payload": prev.payload.model_copy(
                                    update={
                                        "seq": msg.payload.seq,
                                        "append": prev_append + new_append,
                                    },
                                    deep=True,
                                )
                            },
                            deep=True,
                        )
                        continue
                    else:
                        pending_draw_indices.pop(draw_key, None)
                else:
                    pending_draw_indices.pop(draw_key, None)

                msg_copy = msg.model_copy(deep=True)
                if msg.payload.phase == "update":
                    pending_draw_indices[draw_key] = len(result)
                result.append(msg_copy)

            else:
                result.append(msg.model_copy(deep=True))

        return result

    async def broadcast_ephemeral(self, message: ServerMessage, exclude_conn_id: Optional[str] = None):
        for conn in list(self.active_connections.values()):
            if conn.conn_id != exclude_conn_id:
                await conn.enqueue(message)

    async def broadcast_durable(self, message: ServerMessage):
        for conn in list(self.active_connections.values()):
            await conn.enqueue(message)

    def get_user_connections(self, user_id: UUID) -> list[Connection]:
        return [c for c in self.all_connections.values() if c.user_id == user_id and not c.closed]
