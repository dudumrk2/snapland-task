import asyncio
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from snapland.core.domain.user import User
from snapland.core.interfaces.repositories import IUserRepository
from snapland.infrastructure.db.models import UserModel
from snapland.infrastructure.db.repositories.base import BaseRepository


class UserRepository(BaseRepository[UserModel], IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        super().__init__(session, UserModel)

    def _to_domain(self, model: UserModel) -> User:
        return User(
            id=model.id,
            email=model.email,
            display_name=model.display_name,
            password_hash=model.password_hash,
        )

    async def get_by_id(self, user_id: UUID) -> User | None:  # type: ignore[override]
        model = await super().get_by_id(user_id)
        return self._to_domain(model) if model else None

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(UserModel).where(UserModel.email == email)
        result = await asyncio.wait_for(self.session.execute(stmt), timeout=30.0)
        model = result.scalar_one_or_none()
        return self._to_domain(model) if model else None

    async def create(self, user: User) -> User:
        model = UserModel(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            password_hash=user.password_hash or "",
        )
        self.session.add(model)
        await asyncio.wait_for(self.session.flush(), timeout=30.0)
        await asyncio.wait_for(self.session.commit(), timeout=30.0)
        return self._to_domain(model)
