"""Data access for the User aggregate."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.exceptions import EmailAlreadyRegistered
from app.models import User, UserRole


class UserRepository:
    """CRUD over the `users` table. Translates integrity violations into
    domain errors so callers never import `sqlalchemy.exc`.
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, user_id: UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        email: str,
        hashed_password: str,
        full_name: str,
        role: UserRole = UserRole.HR,
    ) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
        )
        self._db.add(user)
        try:
            await self._db.commit()
        except IntegrityError as exc:
            await self._db.rollback()
            raise EmailAlreadyRegistered(
                "A user with this email already exists."
            ) from exc
        await self._db.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """Persist pending mutations to a tracked `user` and refresh."""
        await self._db.commit()
        await self._db.refresh(user)
        return user

    async def list_all(self) -> list[User]:
        result = await self._db.execute(select(User).order_by(User.created_at.desc()))
        return list(result.scalars().all())
