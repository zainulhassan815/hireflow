"""Document upload, retrieval, and deletion."""

from __future__ import annotations

from uuid import UUID, uuid4

from app.adapters.protocols import BlobStorage
from app.domain.exceptions import Forbidden, NotFound
from app.models import Document, User
from app.repositories.document import DocumentRepository


class DocumentService:
    def __init__(self, documents: DocumentRepository, storage: BlobStorage) -> None:
        self._documents = documents
        self._storage = storage

    async def upload(
        self,
        *,
        owner: User,
        filename: str,
        mime_type: str,
        data: bytes,
    ) -> Document:
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

    @staticmethod
    def _ensure_access(doc: Document, actor: User) -> None:
        from app.models import UserRole

        if actor.role == UserRole.ADMIN:
            return
        if doc.owner_id != actor.id:
            raise Forbidden("You do not have access to this document.")
