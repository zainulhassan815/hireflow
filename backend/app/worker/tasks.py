"""Celery task definitions.

Tasks are thin wrappers: build dependencies, call the service, tear down.
All business logic lives in the service layer.

Async services are driven via ``asyncio.run`` so each task gets its own
event loop and a fresh session / httpx client stack.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.worker.celery_app import celery

logger = logging.getLogger(__name__)


# ---------- Document processing ----------


@celery.task(
    name="extract_document_text",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def extract_document_text(self, document_id: str) -> None:
    """Full document processing pipeline.

    Extract text → classify → index embeddings → auto-create candidate
    (if classified as resume). Runs synchronously in the worker process
    with its own sync DB session.
    """
    from app.adapters.chroma_store import ChromaVectorStore
    from app.adapters.classifiers.registry import get_document_classifier
    from app.adapters.minio_storage import MinioBlobStorage
    from app.adapters.text_extractors import CompositeExtractor
    from app.adapters.vision.registry import get_vision_provider
    from app.core.config import settings
    from app.core.db import get_sync_db
    from app.services.embedding_service import EmbeddingService
    from app.services.extraction_service import ExtractionService
    from app.services.sync_candidate_service import SyncCandidateService

    storage = MinioBlobStorage(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )

    vision = get_vision_provider(settings)
    classifier = get_document_classifier(settings)

    try:
        from app.adapters.embeddings.registry import get_embedding_provider

        vector_store = ChromaVectorStore(
            host=settings.chroma_host,
            port=settings.chroma_port,
            embedder=get_embedding_provider(settings),
        )
        embedding = EmbeddingService(vector_store)
    except Exception:
        logger.warning("ChromaDB unavailable, skipping embedding indexing")
        embedding = None

    from app.adapters.contextualizers.registry import get_contextualizer

    contextualizer = get_contextualizer(settings)

    session = get_sync_db()
    try:
        service = ExtractionService(
            session=session,
            extractor=CompositeExtractor(
                strategy=settings.extraction_strategy,
                infer_table_structure=settings.extraction_infer_tables,
                vision=vision,
            ),
            classifier=classifier,
            storage_get=storage.get_sync,
            embedding=embedding,
            contextualizer=contextualizer,
            on_ready=SyncCandidateService(session).handle_document_ready,
        )
        service.process(UUID(document_id))
    except Exception as exc:
        logger.exception("task failed for document %s", document_id)
        raise self.retry(exc=exc) from exc
    finally:
        session.close()


# ---------- Gmail sync ----------


@celery.task(
    name="sync_all_gmail_connections",
    bind=True,
    acks_late=True,
)
def sync_all_gmail_connections(self) -> None:
    """Fan-out: enumerate connections, enqueue one per-user sync task each.

    Intentionally contains no business logic. A failure here only
    affects the current tick; the next beat will retry the fan-out.
    """
    connection_ids = asyncio.run(_load_connection_ids())
    for connection_id in connection_ids:
        sync_gmail_connection.delay(str(connection_id))
    logger.info("gmail sync fan-out: enqueued %d per-user tasks", len(connection_ids))


@celery.task(
    name="sync_gmail_connection",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    retry_backoff=True,
    retry_backoff_max=600,
    acks_late=True,
)
def sync_gmail_connection(self, connection_id: str) -> None:
    """Sync one user's Gmail account.

    Retries only on transient exceptions (HTTP timeouts, network
    errors from httpx). Application-level failures (e.g.
    ``UnsupportedFileType`` from `DocumentService.upload`) are caught
    inside the service and recorded on the claim row; they never
    trigger a retry of the whole user sync.
    """
    import httpx

    try:
        asyncio.run(_run_sync(UUID(connection_id)))
    except (httpx.TransportError, httpx.TimeoutException) as exc:
        logger.warning("transient gmail error on %s: %s; retrying", connection_id, exc)
        raise self.retry(exc=exc) from exc
    except Exception:
        # Anything else — log and give up. Rerunning won't help.
        logger.exception("gmail sync failed permanently for %s", connection_id)
        raise


# ---------- Async helpers ----------


async def _load_connection_ids() -> list[UUID]:
    from app.core.db import WorkerSessionLocal
    from app.repositories.gmail_connection import GmailConnectionRepository

    async with WorkerSessionLocal() as session:
        repo = GmailConnectionRepository(session)
        return [c.id for c in await repo.list_all()]


async def _run_sync(connection_id: UUID) -> None:
    from app.adapters.gmail_api import GoogleGmailApi
    from app.adapters.gmail_oauth import GoogleGmailOAuth
    from app.adapters.minio_storage import MinioBlobStorage
    from app.core.config import settings
    from app.core.db import WorkerSessionLocal
    from app.repositories.activity_log import ActivityLogRepository
    from app.repositories.document import DocumentRepository
    from app.repositories.gmail_connection import GmailConnectionRepository
    from app.repositories.gmail_ingested_message import (
        GmailIngestedMessageRepository,
    )
    from app.repositories.user import UserRepository
    from app.services.activity_service import ActivityService
    from app.services.document_service import DocumentService
    from app.services.gmail_sync_service import GmailSyncService

    if not (
        settings.gmail_client_id
        and settings.gmail_client_secret
        and settings.gmail_redirect_uri
    ):
        logger.warning("gmail sync triggered but OAuth is not configured")
        return

    oauth = GoogleGmailOAuth(
        client_id=settings.gmail_client_id,
        client_secret=settings.gmail_client_secret.get_secret_value(),
        redirect_uri=settings.gmail_redirect_uri,
    )
    api = GoogleGmailApi()

    storage = MinioBlobStorage(
        endpoint=settings.storage_endpoint,
        access_key=settings.storage_access_key,
        secret_key=settings.storage_secret_key,
        bucket=settings.storage_bucket,
        region=settings.storage_region,
    )

    async with WorkerSessionLocal() as session:
        documents_repo = DocumentRepository(session)
        document_service = DocumentService(
            documents_repo,
            storage,
            max_file_size_bytes=settings.max_file_size_mb * 1024 * 1024,
        )
        sync_service = GmailSyncService(
            oauth=oauth,
            api=api,
            connections=GmailConnectionRepository(session),
            ingested=GmailIngestedMessageRepository(session),
            users=UserRepository(session),
            documents=document_service,
            activity=ActivityService(ActivityLogRepository(session)),
            max_messages_per_run=settings.gmail_sync_max_messages_per_run,
            initial_window_days=settings.gmail_sync_initial_window_days,
            claim_timeout_minutes=settings.gmail_sync_claim_timeout_minutes,
        )
        await sync_service.sync(connection_id)
