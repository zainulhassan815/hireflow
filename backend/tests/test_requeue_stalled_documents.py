"""Recovery for documents a dying worker left stuck in PROCESSING.

``ExtractionService.process`` skips anything that isn't PENDING, so a
row stranded mid-extraction is never revisited — ``acks_late`` redelivers
the task once, that run hits the guard and acks, and the document stays
unindexed forever. The sweep is what breaks that.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select, text

from app.core.config import settings
from app.core.db import SessionLocal
from app.models import Document, DocumentStatus
from app.worker.tasks import requeue_stalled_documents


async def _seed(owner_id, *, status: DocumentStatus, filename: str, age_minutes: int):
    """Insert a document and backdate ``updated_at``.

    The column carries ``onupdate=now()``, so the age has to be forced
    with SQL rather than assigned on the model.
    """
    async with SessionLocal() as session:
        doc = Document(
            id=uuid4(),
            owner_id=owner_id,
            filename=filename,
            mime_type="application/pdf",
            size_bytes=1024,
            storage_key=f"test/{filename}",
            status=status,
        )
        session.add(doc)
        await session.commit()
        await session.execute(
            text("update documents set updated_at = :ts where id = :id"),
            {
                "ts": datetime.now(UTC) - timedelta(minutes=age_minutes),
                "id": doc.id,
            },
        )
        await session.commit()
        return doc.id


async def _status(document_id) -> DocumentStatus:
    async with SessionLocal() as session:
        return (
            await session.execute(
                select(Document.status).where(Document.id == document_id)
            )
        ).scalar_one()


@pytest.fixture
def stall_timeout() -> int:
    return settings.document_stall_timeout_minutes


async def test_stalled_document_is_reset_and_requeued(
    hr_user, enqueued_tasks, stall_timeout
) -> None:
    doc_id = await _seed(
        hr_user.id,
        status=DocumentStatus.PROCESSING,
        filename="stuck.pdf",
        age_minutes=stall_timeout + 5,
    )

    assert requeue_stalled_documents() == 1

    assert await _status(doc_id) is DocumentStatus.PENDING
    assert enqueued_tasks.for_task("extract_document_text") == [(str(doc_id),)]


async def test_document_processing_right_now_is_left_alone(
    hr_user, enqueued_tasks
) -> None:
    """A worker mid-extraction must not have its row yanked out from
    under it — that would run two extractions on one document."""
    doc_id = await _seed(
        hr_user.id,
        status=DocumentStatus.PROCESSING,
        filename="live.pdf",
        age_minutes=0,
    )

    assert requeue_stalled_documents() == 0

    assert await _status(doc_id) is DocumentStatus.PROCESSING
    assert enqueued_tasks.for_task("extract_document_text") == []


@pytest.mark.parametrize(
    "status", [DocumentStatus.READY, DocumentStatus.FAILED, DocumentStatus.PENDING]
)
async def test_other_statuses_are_never_touched(
    hr_user, enqueued_tasks, stall_timeout, status
) -> None:
    doc_id = await _seed(
        hr_user.id,
        status=status,
        filename=f"{status.value}.pdf",
        age_minutes=stall_timeout + 60,
    )

    assert requeue_stalled_documents() == 0

    assert await _status(doc_id) is status
    assert enqueued_tasks.for_task("extract_document_text") == []


async def test_reset_commits_before_the_task_is_enqueued(
    hr_user, enqueued_tasks, stall_timeout
) -> None:
    """Ordering is the whole point: if the task ran while the row still
    said PROCESSING it would hit the same skip guard and strand the
    document again."""
    seen: list[DocumentStatus] = []
    doc_id = await _seed(
        hr_user.id,
        status=DocumentStatus.PROCESSING,
        filename="order.pdf",
        age_minutes=stall_timeout + 5,
    )

    from app.core.db import get_sync_db

    def _record(*_args, **_kwargs) -> None:
        probe = get_sync_db()
        try:
            seen.append(
                probe.execute(
                    select(Document.status).where(Document.id == doc_id)
                ).scalar_one()
            )
        finally:
            probe.close()

    from app.worker import tasks as worker_tasks

    original = worker_tasks.extract_document_text.delay
    worker_tasks.extract_document_text.delay = _record
    try:
        requeue_stalled_documents()
    finally:
        worker_tasks.extract_document_text.delay = original

    assert seen == [DocumentStatus.PENDING]
