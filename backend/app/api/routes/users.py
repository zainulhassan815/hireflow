"""User administration endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, UserServiceDep
from app.schemas.auth import UserResponse

router = APIRouter()


@router.get("", response_model=list[UserResponse])
async def list_users(
    current_user: CurrentUser, users: UserServiceDep
) -> list[UserResponse]:
    """List all users. Admin only."""
    result = await users.list_all(actor=current_user)
    return [UserResponse.model_validate(u) for u in result]
