"""Adapter interfaces (Protocols).

One Protocol per collaborator whose implementation is plausibly swappable:
Argon2 → bcrypt, Redis denylist → Postgres table, stub email → SES, etc.
Concrete implementations live in sibling modules.

Single-implementation collaborators (e.g. the SQLAlchemy-backed repositories)
intentionally *don't* get a Protocol — that would be ceremony. Introduce one
the first time a second implementation shows up.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol, runtime_checkable
from uuid import UUID

# ---------- Tokens ----------


class TokenType(StrEnum):
    ACCESS = "access"
    REFRESH = "refresh"


@dataclass(frozen=True, slots=True)
class TokenPayload:
    sub: UUID
    jti: str
    type: TokenType
    exp: datetime
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def remaining_ttl_seconds(self) -> int:
        """Seconds until `exp`, clamped at 0."""
        return max(0, int((self.exp - datetime.now(UTC)).total_seconds()))


@runtime_checkable
class TokenIssuer(Protocol):
    def issue_access(
        self, user_id: UUID, extra_claims: dict[str, Any] | None = None
    ) -> str: ...

    def issue_refresh(self, user_id: UUID) -> str: ...

    def decode(self, token: str, expected: TokenType) -> TokenPayload:
        """Return the decoded payload. Raise `InvalidToken` on any failure."""
        ...


# ---------- Passwords ----------


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, password: str) -> str: ...

    def verify(self, password: str, password_hash: str) -> bool: ...

    def needs_rehash(self, password_hash: str) -> bool: ...


# ---------- Token stores ----------


@runtime_checkable
class RevocationStore(Protocol):
    async def revoke(self, jti: str, ttl_seconds: int) -> None: ...

    async def is_revoked(self, jti: str) -> bool: ...


@runtime_checkable
class ResetTokenStore(Protocol):
    async def issue(self, user_id: UUID, ttl_seconds: int) -> str: ...

    async def consume(self, token: str) -> UUID | None: ...


# ---------- Email ----------


@runtime_checkable
class EmailSender(Protocol):
    async def send_password_reset(self, to: str, reset_url: str) -> None: ...


# ---------- Blob storage ----------


@dataclass(frozen=True, slots=True)
class StoredBlob:
    key: str
    size: int
    etag: str


@runtime_checkable
class BlobStorage(Protocol):
    async def put(self, key: str, data: bytes, content_type: str) -> StoredBlob: ...

    async def get(self, key: str) -> bytes: ...

    async def delete(self, key: str) -> None: ...

    async def presigned_url(self, key: str, expires_seconds: int = 3600) -> str: ...


# ---------- Vision OCR ----------


@runtime_checkable
class VisionProvider(Protocol):
    """Extract text from an image using OCR or a vision-capable LLM.

    Implementations are synchronous (called from Celery workers).
    """

    def extract_text_from_image(
        self, image: bytes, *, prompt: str | None = None
    ) -> str: ...


# ---------- Text extraction ----------


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str
    page_count: int | None = None


@runtime_checkable
class TextExtractor(Protocol):
    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        """Extract text from a document. Runs synchronously (called from a
        Celery worker, not the async event loop).

        Raises ``UnsupportedFileType`` if the MIME type is not handled.
        """
        ...

    def supports(self, mime_type: str) -> bool: ...
