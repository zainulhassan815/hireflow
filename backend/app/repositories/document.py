"""Data access for the Document aggregate."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Document, DocumentStatus, DocumentType

# Cap on chars passed to websearch_to_tsquery. Prevents pasted-in
# job descriptions from blowing tsquery cost. F88.a.
_MAX_QUERY_CHARS = 1024

# pg_trgm similarity cutoff for the fuzzy-search fallback (F88.c).
# 0.25 catches single-letter typos in short filenames while
# rejecting unrelated terms.
_TRGM_THRESHOLD = 0.25


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

    async def search_by_metadata(
        self,
        *,
        document_type: DocumentType | None = None,
        skills: list[str] | None = None,
        min_experience_years: int | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        limit: int = 50,
        owner_id: UUID | None = None,
    ) -> list[Document]:
        """Filter documents by structured metadata fields.

        ``owner_id`` scopes results to a single user; pass ``None`` for an
        unscoped query (admin-level access). Required by F86 search-scoping.
        """
        stmt = select(Document).where(Document.status == DocumentStatus.READY)

        if owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)

        if document_type is not None:
            stmt = stmt.where(Document.document_type == document_type)

        if skills:
            for skill in skills:
                stmt = stmt.where(
                    Document.metadata_["skills"].astext.ilike(f"%{skill}%")
                )

        if min_experience_years is not None:
            stmt = stmt.where(
                Document.metadata_["experience_years"].as_integer()
                >= min_experience_years
            )

        if date_from is not None:
            stmt = stmt.where(Document.created_at >= date_from)

        if date_to is not None:
            stmt = stmt.where(Document.created_at <= date_to)

        stmt = stmt.order_by(Document.created_at.desc()).limit(limit)

        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_many(self, document_ids: list[UUID]) -> dict[UUID, Document]:
        """Fetch multiple documents by ID. Returns a dict keyed by ID."""
        if not document_ids:
            return {}
        result = await self._db.execute(
            select(Document).where(Document.id.in_(document_ids))
        )
        docs = result.scalars().all()
        return {doc.id: doc for doc in docs}

    async def full_text_search(
        self,
        query: str,
        *,
        limit: int = 30,
        owner_id: UUID | None = None,
    ) -> list[tuple[Document, float]]:
        """Lexical retrieval via Postgres FTS, ranked by ts_rank_cd.

        Uses ``websearch_to_tsquery`` so the user's natural-language query
        is tokenized server-side with the same ``english`` analyzer that
        powers the indexed tsvector — punctuation and stopwords are
        handled consistently on both sides. Compared to ``plainto_tsquery``,
        ``websearch_to_tsquery`` (F88.a) additionally supports:

        * Quoted phrases — ``"machine learning"`` keeps tokens adjacent.
        * Explicit ``OR`` — ``python OR golang``.
        * Negation — ``python -java``.

        Plain unquoted multi-word queries still AND, so existing call
        sites are unaffected.

        Returns ``(doc, score)`` pairs ordered by descending rank.
        Documents without indexable text or with no term overlap are
        excluded.

        ``owner_id`` scopes results to a single user; pass ``None`` for
        an unscoped query (admin-level access). F86 added this so search
        respects ownership the same way the documents endpoints do.
        """
        query = query.strip()
        if not query:
            return []

        # Bound tsquery cost on pasted-in job descriptions etc.
        # Postgres handles long inputs but term count drives the scan
        # cost on large corpora.
        if len(query) > _MAX_QUERY_CHARS:
            query = query[:_MAX_QUERY_CHARS]

        ts_query = func.websearch_to_tsquery("english", query)
        rank = func.ts_rank_cd(Document.search_tsv, ts_query).label("rank")

        stmt = (
            select(Document, rank)
            .where(Document.status == DocumentStatus.READY)
            .where(Document.search_tsv.op("@@")(ts_query))
        )

        if owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)

        stmt = stmt.order_by(rank.desc()).limit(limit)

        result = await self._db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]

    async def fuzzy_search(
        self,
        query: str,
        *,
        limit: int = 10,
        owner_id: UUID | None = None,
        threshold: float = _TRGM_THRESHOLD,
    ) -> list[tuple[Document, float]]:
        """Trigram-similarity search over filename + body (F88.c).

        Used by the search service as a fallback when ``full_text_search``
        returns zero hits — a small concession to typo tolerance without
        muddying ranking on good queries. Filename matches ride the
        ``documents_filename_trgm_idx`` GIN index; body matches scan
        unindexed (acceptable for our corpus size; if extracted_text
        grows hot enough to matter, add a GIN trigram index then).

        Uses ``strict_word_similarity`` (not plain ``word_similarity``).
        On long body text ``word_similarity`` finds a fragment match
        anywhere in any token and produces score noise around ~0.28
        for unrelated docs — every doc surfaces. ``strict_word_similarity``
        requires the matched window to align with word boundaries, which
        cleanly separates real matches (~0.27 for a one-letter typo on
        ``python``) from noise (~0.13–0.17). Filename behavior is
        unchanged because filename "words" already align after F87's
        ``regexp_replace`` swap.

        The doc's score is the max of its filename and body strict
        similarity. Returns ``(doc, similarity)`` ordered desc.
        Pass ``owner_id`` for per-user scoping (F86).
        """
        query = query.strip()
        if not query:
            return []

        sim_filename = func.strict_word_similarity(query, Document.filename)
        sim_body = func.strict_word_similarity(
            query, func.coalesce(Document.extracted_text, "")
        )
        # GREATEST handles the case where one side is below threshold.
        sim = func.greatest(sim_filename, sim_body).label("sim")

        stmt = (
            select(Document, sim)
            .where(Document.status == DocumentStatus.READY)
            .where(sim >= threshold)
        )

        if owner_id is not None:
            stmt = stmt.where(Document.owner_id == owner_id)

        stmt = stmt.order_by(sim.desc()).limit(limit)

        result = await self._db.execute(stmt)
        return [(row[0], float(row[1])) for row in result.all()]
