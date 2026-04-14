"""Administrative user queries."""

from __future__ import annotations

from app.domain.authorization import Authorizer
from app.models import User
from app.repositories.user import UserRepository


class UserService:
    def __init__(self, users: UserRepository) -> None:
        self._users = users

    async def list_all(self, *, actor: User) -> list[User]:
        Authorizer.ensure_can_manage_users(actor)
        return await self._users.list_all()
