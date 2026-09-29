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
            pipe.hset("presence:names", str(user_id), display_name)
            await pipe.execute()

    async def remove(self, user_id: UUID, conn_id: str) -> bool:
        await self.redis.zrem("presence:global", f"{user_id}:{conn_id}")
        
        cursor = 0
        has_more = False
        while True:
            cursor, keys = await self.redis.zscan("presence:global", cursor=cursor, match=f"{user_id}:*")
            if keys:
                has_more = True
                break
            if cursor == 0:
                break
                
        if not has_more:
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
            if name:
                name_str = name.decode("utf-8") if isinstance(name, bytes) else str(name)
                result.append(PresenceUser(user_id=UUID(uid_str), display_name=name_str))
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
        
        expired_users = set()
        for member in expired:
            try:
                m_str = member.decode("utf-8") if isinstance(member, bytes) else str(member)
                uid_str = m_str.split(":")[0]
                expired_users.add(uid_str)
            except Exception:
                pass
                
        fully_left = []
        for uid_str in expired_users:
            cursor = 0
            has_more = False
            while True:
                cursor, keys = await self.redis.zscan("presence:global", cursor=cursor, match=f"{uid_str}:*")
                if keys:
                    has_more = True
                    break
                if cursor == 0:
                    break
            if not has_more:
                fully_left.append(UUID(uid_str))
                await self.redis.hdel("presence:names", uid_str)  # type: ignore[misc]
                
        return fully_left
