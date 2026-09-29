import asyncio
import logging
from typing import Dict, Optional
from uuid import UUID

import orjson
from fastapi import WebSocket

from snapland.core.domain.user import User
from snapland.core.domain.ws_messages import RemoteDrawMessage, ServerMessage

logger = logging.getLogger(__name__)

try:
    from prometheus_client import Counter
    WS_MESSAGES_DROPPED_TOTAL = Counter(
        "ws_messages_dropped_total",
        "Total dropped ephemeral messages due to full queue",
        ["reason"],
    )
except Exception:
    WS_MESSAGES_DROPPED_TOTAL = None  # type: ignore[assignment]


class Connection:
    def __init__(self, websocket: WebSocket, user_id: UUID, conn_id: str):
        self.websocket = websocket
        self.user_id = user_id
        self.conn_id = conn_id
        self.queue: asyncio.Queue[ServerMessage] = asyncio.Queue(maxsize=256)
        self.writer_task: Optional[asyncio.Task] = None
        self.closed = False
        self.dropped_count = 0
        self.user: Optional[User] = None
        
    async def enqueue(self, message: ServerMessage) -> None:
        if self.closed:
            return
            
        is_durable = message.type in ("AREA_SAVED", "AREA_UPDATED", "AREA_DELETED")
        
        # HLD 9.3: If durable message cannot be enqueued, close with 1013
        # If ephemeral, drop oldest ephemeral.
        if self.queue.full():
            if is_durable:
                self.closed = True
                await self.websocket.close(code=1013)
                return
            else:
                # drop oldest
                try:
                    self.queue.get_nowait()
                    self.dropped_count += 1
                    if WS_MESSAGES_DROPPED_TOTAL is not None:
                        WS_MESSAGES_DROPPED_TOTAL.labels(reason="queue_full").inc()
                except asyncio.QueueEmpty:
                    pass
                    
        try:
            self.queue.put_nowait(message)
        except asyncio.QueueFull:
            if is_durable:
                self.closed = True
                await self.websocket.close(code=1013)


class WebSocketManager:
    def __init__(self):
        self.active_connections: Dict[str, Connection] = {}

    @property
    def total_dropped_count(self) -> int:
        return sum(c.dropped_count for c in self.active_connections.values())

    async def connect(self, websocket: WebSocket, user_id: UUID, conn_id: str) -> Connection:
        await websocket.accept()
        conn = Connection(websocket, user_id, conn_id)
        self.active_connections[conn_id] = conn
        
        conn.writer_task = asyncio.create_task(self._writer(conn))
        return conn

    async def disconnect(self, conn_id: str):
        conn = self.active_connections.pop(conn_id, None)
        if conn:
            conn.closed = True
            if conn.writer_task:
                conn.writer_task.cancel()
                
    async def _writer(self, conn: Connection):
        try:
            while not conn.closed:
                msg = await conn.queue.get()
                batch = [msg]
                
                # HLD 9.3: micro-batch window 50ms for ephemeral messages
                # If msg is durable (or a durable message arrives), flush immediately.
                is_durable = msg.type in ("AREA_SAVED", "AREA_UPDATED", "AREA_DELETED")
                if not is_durable:
                    deadline = asyncio.get_running_loop().time() + 0.05
                    while True:
                        remaining = deadline - asyncio.get_running_loop().time()
                        if remaining <= 0:
                            break
                        try:
                            m = await asyncio.wait_for(conn.queue.get(), timeout=remaining)
                            batch.append(m)
                            if m.type in ("AREA_SAVED", "AREA_UPDATED", "AREA_DELETED"):
                                break
                        except asyncio.TimeoutError:
                            break
                else:
                    while not conn.queue.empty():
                        m = conn.queue.get_nowait()
                        batch.append(m)
                
                coalesced = self._coalesce(batch)
                
                data = [m.model_dump(exclude_none=True) for m in coalesced]
                await conn.websocket.send_text(orjson.dumps(data).decode("utf-8"))
                
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.warning("WebSocket writer error on conn %s: %s", conn.conn_id, e)
            conn.closed = True

    def _coalesce(self, batch: list[ServerMessage]) -> list[ServerMessage]:
        cursors: dict[UUID, ServerMessage] = {}
        draws: dict[str, RemoteDrawMessage] = {}
        
        result: list[ServerMessage] = []
        for msg in batch:
            if msg.type == "CURSOR_MOVE":
                cursors[msg.payload.userId] = msg
            elif msg.type == "REMOTE_DRAW" and msg.payload.phase == "update":
                shape_id = msg.payload.shapeId
                if shape_id in draws:
                    prev = draws[shape_id]
                    # contiguous merge
                    if prev.payload.seq is not None and msg.payload.seq is not None and prev.payload.seq + 1 == msg.payload.seq:
                        prev.payload.seq = msg.payload.seq
                        if prev.payload.append is not None and msg.payload.append is not None:
                            prev.payload.append.extend(msg.payload.append)
                    else:
                        result.append(prev)
                        draws[shape_id] = msg
                else:
                    draws[shape_id] = msg
            else:
                result.append(msg)
                
        for c in cursors.values():
            result.append(c)
        for d in draws.values():
            result.append(d)
            
        return result
        
    async def broadcast_ephemeral(self, message: ServerMessage, exclude_conn_id: Optional[str] = None):
        for conn_id, conn in self.active_connections.items():
            if conn_id != exclude_conn_id:
                await conn.enqueue(message)
                
    async def broadcast_durable(self, message: ServerMessage):
        for conn in self.active_connections.values():
            await conn.enqueue(message)

    def get_user_connections(self, user_id: UUID) -> list[Connection]:
        return [c for c in self.active_connections.values() if c.user_id == user_id]
