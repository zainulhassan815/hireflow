"""Admin-gated user administration endpoints."""

from fastapi import APIRouter
from sqlalchemy import select

from app.api.deps import DbSession, RequireAdmin
from app.models import User
from app.schemas.auth import UserResponse

router = APIRouter()


@router.get("", response_model=list[UserResponse])
async def list_users(db: DbSession, _admin: RequireAdmin) -> list[UserResponse]:
    """List all users. Admin only."""
    result = await db.execute(select(User).order_by(User.created_at.desc()))
    users = result.scalars().all()
    return [UserResponse.model_validate(u) for u in users]
