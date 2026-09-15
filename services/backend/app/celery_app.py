from celery import Celery
from .config import settings

celery_app = Celery(
    "rag_harness",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["app.tasks"],
)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_transport_options={"visibility_timeout": settings.celery_visibility_timeout},
    result_backend_transport_options={"global_keyprefix": "ragharness_"},
    result_expires=settings.celery_result_expires,
)
