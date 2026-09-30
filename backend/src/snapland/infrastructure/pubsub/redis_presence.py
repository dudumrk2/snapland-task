import time
from typing import Sequence
from uuid import UUID

from redis.asyncio import Redis

from snapland.core.domain.ws_messages import PresenceUser
from snapland.core.interfaces.realtime import IPresenceStore


class RedisPresenceStore(IPresenceStore):
    def __init__(self, redis: Redis):
        self.redis = redis

    async def heartbeat(self, user_id: UUID, conn_id: str, display_name: str) -> None:
        now = int(time.time() * 1000)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zadd("presence:global", {f"{user_id}:{conn_id}": now})
            pipe.sadd(f"presence:conns:{user_id}", conn_id)
            pipe.expire(f"presence:conns:{user_id}", 60)
            if display_name and display_name != "User":
                pipe.hset("presence:names", str(user_id), display_name)
            await pipe.execute()

    async def heartbeat_batch(self, items: Sequence[tuple[UUID, str, str]]) -> None:
        if not items:
            return
        now = int(time.time() * 1000)
        async with self.redis.pipeline(transaction=False) as pipe:
            for user_id, conn_id, display_name in items:
                pipe.zadd("presence:global", {f"{user_id}:{conn_id}": now})
                pipe.sadd(f"presence:conns:{user_id}", conn_id)
                pipe.expire(f"presence:conns:{user_id}", 60)
                if display_name and display_name != "User":
                    pipe.hset("presence:names", str(user_id), display_name)
            await pipe.execute()

    async def add_connection(self, user_id: UUID, conn_id: str, display_name: str) -> bool:
        """Adds a connection and returns True if this is the user's first active connection."""
        now = int(time.time() * 1000)
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.scard(f"presence:conns:{user_id}")
            pipe.zadd("presence:global", {f"{user_id}:{conn_id}": now})
            pipe.sadd(f"presence:conns:{user_id}", conn_id)
            pipe.expire(f"presence:conns:{user_id}", 60)
            if display_name and display_name != "User":
                pipe.hset("presence:names", str(user_id), display_name)
            results = await pipe.execute()
        prev_count = results[0]
        return prev_count == 0

    async def remove(self, user_id: UUID, conn_id: str) -> bool:
        async with self.redis.pipeline(transaction=True) as pipe:
            pipe.zrem("presence:global", f"{user_id}:{conn_id}")
            pipe.srem(f"presence:conns:{user_id}", conn_id)
            pipe.scard(f"presence:conns:{user_id}")
            results = await pipe.execute()
        remaining_count = results[2]
        if remaining_count == 0:
            await self.redis.hdel("presence:names", str(user_id))  # type: ignore[misc]
            return True
        return False

    async def snapshot(self) -> Sequence[PresenceUser]:
        now = int(time.time() * 1000)
        threshold = now - 30000
        members = await self.redis.zrangebyscore("presence:global", threshold, "+inf")
        user_ids = set()
        for member in members:
            try:
                m_str = member.decode("utf-8") if isinstance(member, bytes) else str(member)
                uid_str = m_str.split(":")[0]
                user_ids.add(uid_str)
            except Exception:
                pass

        if not user_ids:
            return []

        users_list = list(user_ids)
        names = await self.redis.hmget("presence:names", users_list)  # type: ignore[misc]

        result = []
        for uid_str, name in zip(users_list, names):
            name_str = name.decode("utf-8") if isinstance(name, bytes) else (str(name) if name else "User")
            result.append(PresenceUser(userId=UUID(uid_str), displayName=name_str))
        return result

    async def reap_expired(self) -> Sequence[UUID]:
        lock_key = "presence:reap:lock"
        acquired = await self.redis.set(lock_key, "1", nx=True, px=8000)
        if not acquired:
            return []

        now = int(time.time() * 1000)
        threshold = now - 30000

        expired = await self.redis.zrangebyscore("presence:global", "-inf", threshold)
        if not expired:
            return []

        await self.redis.zrem("presence:global", *expired)

        expired_by_user: dict[str, list[str]] = {}
        for member in expired:
            try:
                m_str = member.decode("utf-8") if isinstance(member, bytes) else str(member)
                parts = m_str.split(":", 1)
                uid_str = parts[0]
                cid = parts[1] if len(parts) > 1 else ""
                expired_by_user.setdefault(uid_str, []).append(cid)
            except Exception:
                pass

        fully_left: list[UUID] = []
        async with self.redis.pipeline(transaction=True) as pipe:
            for uid_str, cids in expired_by_user.items():
                if cids:
                    pipe.srem(f"presence:conns:{uid_str}", *cids)
                pipe.scard(f"presence:conns:{uid_str}")
            results = await pipe.execute()

        idx = 0
        for uid_str, cids in expired_by_user.items():
            if cids:
                idx += 1  # skip srem result
            rem_count = results[idx]
            idx += 1
            if rem_count == 0:
                fully_left.append(UUID(uid_str))
                await self.redis.hdel("presence:names", uid_str)  # type: ignore[misc]

        return fully_left
