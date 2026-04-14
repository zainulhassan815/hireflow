"""Auth business logic: registration and credential verification."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import (
    hash_password,
    password_hash_needs_rehash,
    verify_password,
)
from app.models import User, UserRole


async def register_user(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    role: UserRole = UserRole.HR,
) -> User:
    user = User(
        email=email.lower(),
        hashed_password=hash_password(password),
        full_name=full_name,
        role=role,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email already exists.",
        ) from exc
    await db.refresh(user)
    return user


async def authenticate_user(db: AsyncSession, *, email: str, password: str) -> User:
    result = await db.execute(select(User).where(User.email == email.lower()))
    user = result.scalar_one_or_none()

    # Constant-time-ish: still hash-verify against a dummy when the user is
    # missing so timing doesn't leak account existence.
    if user is None:
        verify_password(password, _DUMMY_HASH)
        raise _invalid_credentials()

    if not verify_password(password, user.hashed_password):
        raise _invalid_credentials()

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is disabled.",
        )

    # Transparent rehash: if Argon2 params change over time, upgrade on login.
    if password_hash_needs_rehash(user.hashed_password):
        user.hashed_password = hash_password(password)
        await db.commit()
        await db.refresh(user)

    return user


def _invalid_credentials() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid email or password.",
    )


# Precomputed Argon2 hash of an arbitrary string; used to equalize timing
# when the queried email doesn't exist.
_DUMMY_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$"
    "c29tZXNhbHR2YWx1ZQ$Z1qNTf+7M+UqJ7Id9xy4s6cT7ZQJ3XA5VJ7pVlDbXoE"
)
