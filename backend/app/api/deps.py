"""Shared FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import Annotated
from uuid import UUID

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.redis import get_redis
from app.core.security import TokenType, decode_token
from app.models import User, UserRole

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=True)


DbSession = Annotated[AsyncSession, Depends(get_db)]
RedisDep = Annotated[Redis, Depends(get_redis)]


async def get_current_user(
    db: DbSession,
    token: Annotated[str, Depends(oauth2_scheme)],
) -> User:
    credentials_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = decode_token(token, TokenType.ACCESS)
        user_id = UUID(payload["sub"])
    except (jwt.InvalidTokenError, KeyError, ValueError) as exc:
        raise credentials_exc from exc

    user = await db.get(User, user_id)
    if user is None or not user.is_active:
        raise credentials_exc
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]


def require_role(
    *allowed: UserRole,
) -> Callable[[User], Coroutine[None, None, User]]:
    """Dependency factory: 403 unless the caller's role is in `allowed`."""

    async def _checker(current_user: CurrentUser) -> User:
        if current_user.role not in allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You do not have permission to perform this action.",
            )
        return current_user

    return _checker


RequireAdmin = Annotated[User, Depends(require_role(UserRole.ADMIN))]
