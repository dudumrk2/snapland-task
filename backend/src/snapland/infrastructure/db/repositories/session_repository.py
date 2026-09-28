from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from snapland.core.domain.user import Session
from snapland.core.interfaces.repositories import ISessionRepository
from snapland.infrastructure.db.models import SessionModel
from snapland.infrastructure.db.repositories.base import BaseRepository

class SessionRepository(BaseRepository[SessionModel], ISessionRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, SessionModel)

    def _to_domain(self, model: SessionModel) -> Session:
        return Session(
            id=model.id,
            user_id=model.user_id,
            family_id=model.family_id,
            refresh_token_hash=model.refresh_token_hash,
            expires_at=model.expires_at,
            revoked_at=model.revoked_at,
            ip_address=str(model.ip_address) if model.ip_address else "",
            created_at=model.created_at
        )

    async def create(self, session: Session) -> Session:
        model = SessionModel(
            id=session.id,
            user_id=session.user_id,
            family_id=session.family_id,
            refresh_token_hash=session.refresh_token_hash,
            expires_at=datetime.fromisoformat(session.expires_at) if isinstance(session.expires_at, str) else session.expires_at,
            revoked_at=datetime.fromisoformat(session.revoked_at) if isinstance(session.revoked_at, str) and session.revoked_at else session.revoked_at,
            ip_address=session.ip_address,
            created_at=datetime.fromisoformat(session.created_at) if isinstance(session.created_at, str) else session.created_at
        )
        self.session.add(model)
        await self.session.flush()
        return self._to_domain(model)

    async def get_by_token_hash(self, token_hash: str) -> Session | None:
        stmt = select(SessionModel).where(SessionModel.refresh_token_hash == token_hash)
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def revoke(self, session_id: UUID) -> None:
        stmt = (
            update(SessionModel)
            .where(SessionModel.id == session_id)
            .values(revoked_at=datetime.now(timezone.utc))
        )
        await self.session.execute(stmt)

    async def revoke_family(self, family_id: UUID) -> int:
        stmt = (
            update(SessionModel)
            .where(SessionModel.family_id == family_id)
            .where(SessionModel.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return getattr(result, 'rowcount', 0)

    async def revoke_all_for_user(self, user_id: UUID) -> int:
        stmt = (
            update(SessionModel)
            .where(SessionModel.user_id == user_id)
            .where(SessionModel.revoked_at.is_(None))
            .values(revoked_at=datetime.now(timezone.utc))
        )
        result = await self.session.execute(stmt)
        return getattr(result, 'rowcount', 0)
