import typing
import uuid
from fastapi import APIRouter, Depends, Request
from snapland.core.domain.user import User
from snapland.api.v1.auth import get_current_user_id

router = APIRouter(prefix="/users", tags=["users"])

def get_user_repository(request: Request) -> typing.Any:
    return request.app.state.user_repository

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
