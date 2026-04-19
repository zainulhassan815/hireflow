"""Adapter interfaces (Protocols).

One Protocol per collaborator whose implementation is plausibly swappable:
Argon2 → bcrypt, Redis denylist → Postgres table, stub email → SES, etc.
Concrete implementations live in sibling modules.

Single-implementation collaborators (e.g. the SQLAlchemy-backed repositories)
intentionally *don't* get a Protocol — that would be ceremony. Introduce one
the first time a second implementation shows up.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
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


# ---------- LLM ----------


@runtime_checkable
class LlmProvider(Protocol):
    """Text-to-text LLM access.

    Two entry points. ``complete`` is synchronous — call via
    ``asyncio.to_thread`` from async routes, and use directly from
    Celery workers (classifiers, contextualizers). ``stream`` is an
    async generator — consume from async code only; it exists because
    all streaming SDKs we target expose native async APIs and a
    sync-iterator-bridged-via-queue shape would be a workaround.
    """

    def complete(self, system: str, user: str) -> str: ...

    def stream(self, system: str, user: str) -> AsyncIterator[str]:
        """Yield text deltas as the model generates.

        Declared as plain ``def`` returning ``AsyncIterator[str]`` (not
        ``async def``) so implementations are free to use the
        idiomatic ``async def ... yield`` async-generator shape.
        ``@runtime_checkable`` verifies method presence, not the
        sync/async qualifier on the signature.
        """
        ...

    @property
    def model_name(self) -> str: ...


# ---------- Document classification ----------


@dataclass(frozen=True, slots=True)
class ClassificationResult:
    document_type: str  # matches DocumentType enum values
    confidence: float  # 0.0–1.0
    metadata: dict[str, Any]  # skills, experience, education, etc.


@runtime_checkable
class DocumentClassifier(Protocol):
    def classify(self, text: str, filename: str) -> ClassificationResult:
        """Classify a document and extract structured metadata from its text.

        Runs synchronously (called from a Celery worker).
        """
        ...


# ---------- Chunk contextualizer (F82.c) ----------


@runtime_checkable
class ChunkContextualizer(Protocol):
    """Augment retrieval chunks with situational context.

    Runs at index time: for each chunk, produce a 50-100 token
    situating context that the embedder prepends to the chunk text
    before producing the vector. The chunk's displayed text (snippets,
    highlights) is unchanged — contextualization only moves the
    retrieval vector.

    Per Anthropic's 2024 "Contextual Retrieval" paper, published
    -35% retrieval failure reduction vs vanilla embedding.

    Implementations run synchronously (called from Celery worker).
    """

    def contextualize(self, document: Any, chunks: list[Any]) -> list[Any]:
        """Return chunks with ``context`` populated.

        ``document`` is an ORM ``Document``; ``chunks`` is
        ``list[services.chunking.Chunk]``. Typed via ``Any`` here to
        avoid a circular import — the Protocol's job is to describe
        behavior, not enforce types.
        """
        ...

    @property
    def model_name(self) -> str: ...


# ---------- Embedding provider ----------


@runtime_checkable
class EmbeddingProvider(Protocol):
    """Turn text into dense vectors. Provider-agnostic.

    Implementations may be local (sentence-transformers, fastembed) or
    remote (OpenAI, Voyage, Cohere). ``dimension`` and ``model_name``
    travel with the embedder so the vector store can warn on dim
    mismatch and the eval harness can label results.

    Synchronous on purpose — callers running inside an asyncio loop
    should hop to a thread (``asyncio.to_thread``). Local models do
    real CPU work; doing it on the event loop would block.
    """

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Return one vector per input text."""
        ...

    def embed_query(self, text: str) -> list[float]:
        """Return one vector for a search query.

        A separate method so providers that benefit from query/document
        asymmetry (e.g. instruct-tuned models needing a ``query:``
        prefix) can do that internally without leaking the detail.
        """
        ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimension(self) -> int: ...

    @property
    def recommended_distance_threshold(self) -> float:
        """Cosine-distance cutoff above which hits are considered noise.

        Varies per model: bge-small's relevant hits cluster ~0.18-0.30
        so 0.35 is a safe cutoff; MiniLM's distribution is wider. F85.d
        lets each embedder own this so swapping models doesn't silently
        break the threshold. ``SearchService`` uses this when
        ``settings.search_max_distance`` is ``None``; an explicit float
        in settings still overrides (operator knob).
        """
        ...


# ---------- Reranker (F80.5) ----------


@dataclass(frozen=True, slots=True)
class RerankCandidate:
    """A document (or chunk) handed to a reranker.

    ``document_id`` is opaque to the reranker — it's the caller's
    handle to map scores back to its own result objects.
    ``text`` is what the cross-encoder actually reads alongside the
    query; typically the top-scoring chunk per document.
    ``original_score`` / ``metadata`` pass through untouched.
    """

    document_id: UUID
    text: str
    original_score: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Reranker(Protocol):
    """Reorder a small candidate set using (query, text) cross-encoder scoring.

    Typical use: after retrieval returns top-K (say 20) via fast
    bi-encoder similarity, the reranker reads each candidate alongside
    the query simultaneously and returns a better-ordered list. Cost is
    per-query only; no index-time work.

    Called synchronously from the FastAPI request handler; if inference
    is heavy enough to matter, callers should hop to a thread.
    """

    def rerank(
        self,
        query: str,
        candidates: list[RerankCandidate],
        top_n: int | None = None,
    ) -> list[RerankCandidate]:
        """Return candidates reordered by relevance (best first).

        If ``top_n`` is set, truncate to that many items. If ``top_n``
        exceeds ``len(candidates)``, returns all candidates in the new
        order — no padding.
        """
        ...

    @property
    def model_name(self) -> str: ...


# ---------- Vector store ----------


@dataclass(frozen=True, slots=True)
class VectorHit:
    chunk_id: str
    document_id: str
    text: str
    metadata: dict[str, Any]
    distance: float


@runtime_checkable
class VectorStore(Protocol):
    def upsert(
        self,
        document_id: str,
        chunks: list[str],
        metadatas: list[dict[str, Any]],
    ) -> None:
        """Index text chunks for a document. Replaces existing chunks."""
        ...

    def delete(self, document_id: str) -> None:
        """Remove all chunks for a document."""
        ...

    def query(
        self,
        query_text: str,
        n_results: int = 10,
        where: dict[str, Any] | None = None,
    ) -> list[VectorHit]:
        """Semantic search. Returns chunks ranked by relevance."""
        ...


# ---------- Text extraction ----------


@dataclass(frozen=True, slots=True)
class Element:
    """One typed region of a document from layout-aware extraction.

    The ``kind`` comes from the extraction library's taxonomy
    (unstructured's: Title, NarrativeText, ListItem, Table, Header,
    Footer, Address, Image, PageBreak, ...). We keep it as a free-form
    string rather than an enum so a different extractor can slot in
    without a schema change — consumers interpret the string.

    ``order`` preserves the reading order within the document so we can
    reassemble text or re-chunk from the persisted elements without
    another extraction pass.
    """

    kind: str
    text: str
    page_number: int | None
    order: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    text: str
    page_count: int | None = None
    elements: list[Element] = field(default_factory=list)


@runtime_checkable
class TextExtractor(Protocol):
    def extract(self, data: bytes, mime_type: str) -> ExtractionResult:
        """Extract text from a document. Runs synchronously (called from a
        Celery worker, not the async event loop).

        Raises ``UnsupportedFileType`` if the MIME type is not handled.
        """
        ...

    def supports(self, mime_type: str) -> bool: ...


# ---------- Gmail OAuth ----------


@dataclass(frozen=True, slots=True)
class OAuthTokens:
    """What Google returns from the token endpoint."""

    access_token: str
    refresh_token: str | None
    expires_in: int
    scope: str


@runtime_checkable
class GmailOAuth(Protocol):
    def build_authorize_url(self, state: str) -> str: ...

    async def exchange_code(self, code: str) -> OAuthTokens: ...

    async def refresh(self, refresh_token: str) -> OAuthTokens: ...

    async def revoke(self, token: str) -> None: ...

    async def fetch_email(self, access_token: str) -> str: ...


@dataclass(frozen=True, slots=True)
class GmailAttachmentRef:
    """Reference to an attachment inside a Gmail message (pre-download)."""

    attachment_id: str
    filename: str
    mime_type: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class GmailMessageSummary:
    """Minimum info to decide whether to fetch a full message."""

    message_id: str
    thread_id: str


@dataclass(frozen=True, slots=True)
class GmailMessage:
    """Full message with flattened attachment metadata."""

    message_id: str
    thread_id: str
    internal_date_ms: int
    attachments: list[GmailAttachmentRef]


@dataclass(frozen=True, slots=True)
class GmailMessagePage:
    """One page of message IDs from ``messages.list``."""

    messages: list[GmailMessageSummary]
    next_page_token: str | None


class InvalidGrant(Exception):
    """Raised by the OAuth refresh when Google returns ``invalid_grant``.

    Signals that the user has revoked access at ``myaccount.google.com``
    or the refresh token is otherwise dead. Not a domain error —
    callers decide whether to auto-disconnect or propagate.
    """


@runtime_checkable
class GmailApi(Protocol):
    async def list_messages(
        self, access_token: str, *, query: str, page_token: str | None = None
    ) -> GmailMessagePage: ...

    async def get_message(self, access_token: str, message_id: str) -> GmailMessage: ...

    async def download_attachment(
        self, access_token: str, message_id: str, attachment_id: str
    ) -> bytes: ...
