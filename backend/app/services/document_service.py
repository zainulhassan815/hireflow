"""Document upload, retrieval, and deletion."""

from __future__ import annotations

import logging
from uuid import UUID, uuid4

from app.adapters.protocols import BlobStorage, DocumentSimilarityStore, VectorStore
from app.domain.exceptions import (
    FileTooLarge,
    Forbidden,
    NotFound,
    UnsupportedFileType,
)
from app.models import Document, User
from app.repositories.document import DocumentRepository

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = frozenset(
    {
        "application/pdf",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "application/msword",
        "image/png",
        "image/jpeg",
        "image/tiff",
    }
)


class DocumentService:
    def __init__(
        self,
        documents: DocumentRepository,
        storage: BlobStorage,
        *,
        max_file_size_bytes: int,
        vector_store: VectorStore | None = None,
        similarity_store: DocumentSimilarityStore | None = None,
    ) -> None:
        self._documents = documents
        self._storage = storage
        self._max_size = max_file_size_bytes
        self._vector_store = vector_store
        self._similarity_store = similarity_store

    @property
    def max_size_bytes(self) -> int:
        """Upload size cap; used by Gmail sync to pre-filter attachments."""
        return self._max_size

    async def upload(
        self,
        *,
        owner: User,
        filename: str,
        mime_type: str,
        data: bytes,
    ) -> Document:
        if len(data) > self._max_size:
            limit_mb = self._max_size // (1024 * 1024)
            raise FileTooLarge(f"File exceeds {limit_mb} MB limit.")
        if mime_type not in ALLOWED_MIME_TYPES:
            raise UnsupportedFileType(
                f"File type {mime_type!r} is not supported. "
                f"Allowed: PDF, DOCX, DOC, PNG, JPEG, TIFF."
            )

        storage_key = f"{owner.id}/{uuid4()}/{filename}"
        blob = await self._storage.put(storage_key, data, mime_type)
        return await self._documents.create(
            owner_id=owner.id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=blob.size,
            storage_key=blob.key,
        )

    async def get(self, document_id: UUID, *, actor: User) -> Document:
        doc = await self._documents.get(document_id)
        if doc is None:
            raise NotFound("Document not found.")
        self._ensure_access(doc, actor)
        return doc

    async def download(
        self, document_id: UUID, *, actor: User
    ) -> tuple[Document, bytes]:
        doc = await self.get(document_id, actor=actor)
        data = await self._storage.get(doc.storage_key)
        return doc, data

    async def delete(self, document_id: UUID, *, actor: User) -> None:
        doc = await self.get(document_id, actor=actor)
        await self._storage.delete(doc.storage_key)
        if self._vector_store:
            try:
                self._vector_store.delete(str(document_id))
            except Exception:
                logger.warning("failed to remove embeddings for %s", document_id)
        # F89.c — mirror cleanup for the doc-level similarity vector.
        # Chroma's ``delete`` is a no-op on missing ids so this is safe
        # for docs uploaded before F89.c shipped.
        if self._similarity_store:
            try:
                self._similarity_store.delete_document_vector(str(document_id))
            except Exception:
                logger.warning("failed to remove doc-level vector for %s", document_id)
        await self._documents.delete(doc)

    async def list_for_user(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        return await self._documents.list_by_owner(owner_id, limit=limit, offset=offset)

    async def presigned_url(
        self, document_id: UUID, *, actor: User, expires_seconds: int = 3600
    ) -> str:
        doc = await self.get(document_id, actor=actor)
        return await self._storage.presigned_url(doc.storage_key, expires_seconds)

    async def set_author(
        self,
        document_id: UUID,
        *,
        candidate_id: UUID | None,
        actor: User,
    ) -> tuple[Document, bool]:
        """F103.c.2 — manually set or clear ``Document.authored_by_id``.

        Owner-scoped; the operator must own the document **and** the
        candidate (cross-tenant linking is rejected as 404 to keep
        the existence side-channel closed). Stamps
        ``authored_by_source = 'manual'`` on a successful set so
        future F103.c email-match backfills don't overwrite the
        operator's intent.

        Idempotent: returns ``(doc, changed=False)`` when the FK
        + source already match the requested state — caller skips
        the activity-log write and the re-embed enqueue in that
        case.
        """
        from app.models import AuthorSource, UserRole

        doc = await self._documents.get(document_id)
        if doc is None:
            raise NotFound("Document not found.")
        self._ensure_access(doc, actor)

        if candidate_id is not None:
            candidate = await self._documents.get_candidate(candidate_id)
            if candidate is None:
                raise NotFound("Candidate not found.")
            # Cross-tenant: same 404 as a missing candidate so we
            # don't leak the existence of another owner's candidate.
            if actor.role != UserRole.ADMIN and candidate.owner_id != actor.id:
                raise NotFound("Candidate not found.")

        # Idempotent fast path. If the FK + source already match the
        # requested state, return without writing anything. The
        # source check matters because re-PATCH-ing the same
        # candidate after an email-match auto-link should still flip
        # the source to 'manual' — that's a meaningful state change
        # the audit trail wants to record.
        target_source = AuthorSource.MANUAL if candidate_id else None
        if (
            doc.authored_by_id == candidate_id
            and doc.authored_by_source == target_source
        ):
            return doc, False

        doc.authored_by_id = candidate_id
        doc.authored_by_source = target_source
        await self._documents.save(doc)
        return doc, True

    @staticmethod
    def _ensure_access(doc: Document, actor: User) -> None:
        from app.models import UserRole

        if actor.role == UserRole.ADMIN:
            return
        if doc.owner_id != actor.id:
            raise Forbidden("You do not have access to this document.")
