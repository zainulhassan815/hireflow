"""Business-level authorization policy.

Single source of truth for "is actor X allowed to perform action Y on target Z?"
questions. Called from services (for data-plane checks) and occasionally from
routes (for cheap early-exit). HTTP-level guards like
`api.deps.require_role` remain as defense-in-depth.

Methods raise `Forbidden` on denial so services don't have to branch.
"""

from __future__ import annotations

from app.domain.exceptions import Forbidden
from app.models import User, UserRole


class Authorizer:
    @staticmethod
    def ensure_can_manage_users(actor: User) -> None:
        if actor.role != UserRole.ADMIN:
            raise Forbidden("Only administrators can manage users.")
