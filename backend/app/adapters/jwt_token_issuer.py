"""JWT implementation of the `TokenIssuer` protocol."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import jwt
from pydantic import SecretStr

from app.adapters.protocols import TokenPayload, TokenType
from app.domain.exceptions import InvalidToken


class JwtTokenIssuer:
    """Issues and validates HS-signed JWTs.

    Every token carries a `jti` so individual tokens can be revoked (see the
    `RevocationStore`). `decode` enforces the `type` claim so access and
    refresh tokens can't impersonate each other.
    """

    def __init__(
        self,
        *,
        secret: SecretStr,
        algorithm: str,
        access_ttl: timedelta,
        refresh_ttl: timedelta,
    ) -> None:
        self._secret = secret
        self._algorithm = algorithm
        self._access_ttl = access_ttl
        self._refresh_ttl = refresh_ttl

    def issue_access(
        self, user_id: UUID, extra_claims: dict[str, Any] | None = None
    ) -> str:
        return self._encode(
            user_id,
            TokenType.ACCESS,
            self._access_ttl,
            extra_claims,
        )

    def issue_refresh(self, user_id: UUID) -> str:
        return self._encode(user_id, TokenType.REFRESH, self._refresh_ttl)

    def decode(self, token: str, expected: TokenType) -> TokenPayload:
        try:
            raw = jwt.decode(
                token,
                self._secret.get_secret_value(),
                algorithms=[self._algorithm],
            )
        except jwt.InvalidTokenError as exc:
            raise InvalidToken("Token is invalid or expired.") from exc

        if raw.get("type") != expected.value:
            raise InvalidToken(
                f"Expected {expected.value} token, got {raw.get('type')!r}."
            )

        try:
            return TokenPayload(
                sub=UUID(raw["sub"]),
                jti=raw["jti"],
                type=TokenType(raw["type"]),
                exp=datetime.fromtimestamp(raw["exp"], tz=UTC),
                extra={k: v for k, v in raw.items() if k not in _RESERVED_CLAIMS},
            )
        except (KeyError, ValueError) as exc:
            raise InvalidToken("Token payload is malformed.") from exc

    def _encode(
        self,
        user_id: UUID,
        token_type: TokenType,
        ttl: timedelta,
        extra_claims: dict[str, Any] | None = None,
    ) -> str:
        now = datetime.now(UTC)
        payload: dict[str, Any] = {
            "sub": str(user_id),
            "type": token_type.value,
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + ttl,
        }
        if extra_claims:
            payload.update(extra_claims)
        return jwt.encode(
            payload,
            self._secret.get_secret_value(),
            algorithm=self._algorithm,
        )


_RESERVED_CLAIMS = frozenset({"sub", "type", "jti", "iat", "exp"})
