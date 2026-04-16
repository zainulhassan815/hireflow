"""Celery task definitions.

Tasks are thin wrappers: build dependencies, call the service, tear down.
All business logic lives in the service layer.
"""

from __future__ import annotations

import logging
from uuid import UUID

from app.worker.celery_app import celery

logger = logging.getLogger(__name__)


@celery.task(
    name="extract_document_text",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    acks_late=True,
)
def extract_document_text(self, document_id: str) -> None:
    """Full document processing pipeline.

    Extract text → classify → index embeddings. All providers resolved
    fresh from settings on every invocation for runtime flexibility.
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
        vector_store = ChromaVectorStore(
            host=settings.chroma_host, port=settings.chroma_port
        )
        embedding = EmbeddingService(vector_store)
    except Exception:
        logger.warning("ChromaDB unavailable, skipping embedding indexing")
        embedding = None

    session = get_sync_db()
    try:
        service = ExtractionService(
            session=session,
            extractor=CompositeExtractor(vision=vision),
            classifier=classifier,
            storage_get=storage.get_sync,
            embedding=embedding,
        )
        service.process(UUID(document_id))
    except Exception as exc:
        logger.exception("task failed for document %s", document_id)
        raise self.retry(exc=exc) from exc
    finally:
        session.close()
