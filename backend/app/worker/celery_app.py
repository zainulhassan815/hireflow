"""Celery application factory.

Single source of truth for the Celery instance. Both the FastAPI app (to
enqueue tasks) and the worker process (to execute them) import from here.

Start a worker:
    celery -A app.worker.celery_app worker --loglevel=info
"""

from celery import Celery

from app.core.config import settings

celery = Celery(
    "hireflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
)

celery.autodiscover_tasks(["app.worker"])
