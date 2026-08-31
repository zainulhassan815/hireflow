"""Celery application factory.

Single source of truth for the Celery instance. Both the FastAPI app (to
enqueue tasks) and the worker process (to execute them) import from here.

Start a worker:
    celery -A app.worker.celery_app worker --loglevel=info

Start beat (periodic scheduler, runs in its own process):
    celery -A app.worker.celery_app beat --loglevel=info
"""

import sys

from celery import Celery
from celery.schedules import schedule

from app.core.config import settings

celery = Celery(
    "hireflow",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

# macOS: the default prefork pool forks after the parent has touched
# Metal, and a forked child cannot reach MTLCompilerService — the first
# MPS op aborts the process with SIGABRT, killing the task with
# WorkerLostError and stranding its row mid-status. Torch picks MPS
# automatically for the local embedder and reranker, so any task that
# embeds hits this. ``solo`` runs tasks in the main process, so nothing
# forks and MPS keeps working. Linux keeps prefork, where fork is safe
# and concurrency is worth having.
#
# ponytail: platform-wide switch, not per-task. If macOS ever needs real
# worker concurrency, ``--pool=threads`` also avoids the fork; CUDA has
# the same fork restriction, so a GPU Linux box would need the same
# treatment.
if sys.platform == "darwin":
    celery.conf.worker_pool = "solo"

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
    beat_schedule={
        "gmail-sync-fanout": {
            "task": "sync_all_gmail_connections",
            "schedule": schedule(run_every=settings.gmail_sync_interval_minutes * 60),
        },
    },
)

celery.autodiscover_tasks(["app.worker"])
