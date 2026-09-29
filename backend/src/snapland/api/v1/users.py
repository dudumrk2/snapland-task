import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from snapland.api.deps import get_db
from snapland.api.v1.auth import get_current_user_id
from snapland.core.domain.user import User
from snapland.infrastructure.db.repositories.user_repository import UserRepository

router = APIRouter(prefix="/users", tags=["users"])


def get_user_repository(db: AsyncSession = Depends(get_db)):
    return UserRepository(db)

@router.get("/me", response_model=User)
async def get_me(
    user_id: uuid.UUID = Depends(get_current_user_id),
    user_repo = Depends(get_user_repository)
):
    from snapland.core.domain.exceptions import NotFoundError
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise NotFoundError("User not found")
    return user
