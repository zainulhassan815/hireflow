"""Data access for the Document aggregate."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentStatus


class DocumentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get(self, document_id: UUID) -> Document | None:
        return await self._db.get(Document, document_id)

    async def create(
        self,
        *,
        owner_id: UUID,
        filename: str,
        mime_type: str,
        size_bytes: int,
        storage_key: str,
    ) -> Document:
        doc = Document(
            owner_id=owner_id,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            storage_key=storage_key,
            status=DocumentStatus.PENDING,
        )
        self._db.add(doc)
        await self._db.commit()
        await self._db.refresh(doc)
        return doc

    async def save(self, doc: Document) -> Document:
        await self._db.commit()
        await self._db.refresh(doc)
        return doc

    async def delete(self, doc: Document) -> None:
        await self._db.delete(doc)
        await self._db.commit()

    async def list_by_owner(
        self, owner_id: UUID, *, limit: int = 50, offset: int = 0
    ) -> list[Document]:
        result = await self._db.execute(
            select(Document)
            .where(Document.owner_id == owner_id)
            .order_by(Document.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def count_by_owner(self, owner_id: UUID) -> int:
        from sqlalchemy import func

        result = await self._db.execute(
            select(func.count())
            .select_from(Document)
            .where(Document.owner_id == owner_id)
        )
        return result.scalar_one()
