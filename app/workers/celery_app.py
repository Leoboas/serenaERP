from celery import Celery

from app.core.config import get_settings

settings = get_settings()

# `include` is intentional: the worker must register tasks without relying on
# the API process importing a task module as a side effect.
celery_app = Celery(
    "goverp-core-ai",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.workers.ai_worker"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_soft_time_limit=90,
    task_time_limit=120,
    task_track_started=True,
    result_expires=3600,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": 600},
    beat_schedule={
        "dispatch-analysis-outbox": {
            "task": "serenaerp.analysis.dispatch_pending",
            "schedule": settings.analysis_dispatch_interval_seconds,
        }
    },
)
