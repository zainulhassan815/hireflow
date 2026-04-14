"""User administration endpoints."""

from fastapi import APIRouter

from app.api.deps import CurrentUser, UserServiceDep
from app.schemas.auth import UserResponse

router = APIRouter()


@router.get(
    "",
    response_model=list[UserResponse],
    summary="List all users",
    description="Return every registered user. Requires the admin role.",
    responses={
        401: {"description": "Not authenticated"},
        403: {"description": "Caller is not an admin"},
    },
)
async def list_users(
    current_user: CurrentUser, users: UserServiceDep
) -> list[UserResponse]:
    result = await users.list_all(actor=current_user)
    return [UserResponse.model_validate(u) for u in result]
