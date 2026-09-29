from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from snapland.config import settings
from snapland.core.domain.events import DomainEvent
from snapland.core.services.area_service import AreaService
from snapland.core.services.audit_service import AuditService
from snapland.core.services.auth_service import AuthService
from snapland.core.services.spatial_service import SpatialService
from snapland.infrastructure.cache.cache_repository import CacheRepository
from snapland.infrastructure.db.repositories.area_repository import AreaRepository
from snapland.infrastructure.db.repositories.session_repository import SessionRepository
from snapland.infrastructure.db.repositories.user_repository import UserRepository
from snapland.infrastructure.db.session import SessionLocal


async def get_db() -> AsyncSession: # type: ignore
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

def get_redis(request: Request):
    return request.app.state.redis

def get_rate_limiter(request: Request):
    return request.app.state.rate_limiter

def get_auth_service(db: AsyncSession = Depends(get_db), redis = Depends(get_redis)):
    user_repo = UserRepository(db)
    session_repo = SessionRepository(db)
    cache_repo = CacheRepository(redis)
    return AuthService(
        user_repo=user_repo,
        session_repo=session_repo,
        cache_repo=cache_repo,
        jwt_private_key=settings.JWT_PRIVATE_KEY
    )

class DummyEventPublisher:
    async def publish(self, event: DomainEvent) -> None:
        pass

def get_area_service(db: AsyncSession = Depends(get_db), redis = Depends(get_redis)):
    repo = AreaRepository(db)
    cache = CacheRepository(redis)
    spatial = SpatialService()
    audit = AuditService()
    events = DummyEventPublisher()
    return AreaService(
        repo=repo,
        spatial=spatial,
        cache=cache,
        events=events,
        audit=audit
    )

def get_audit_service():
    return AuditService()
