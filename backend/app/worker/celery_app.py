from celery import Celery
from app.core.config import settings

celery = Celery(
    "legal_assist",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["app.worker.tasks"],
)

celery.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_time_limit=900,        # 15 min hard kill
    task_soft_time_limit=780,   # 13 min soft — lets task clean up
    worker_prefetch_multiplier=1,  # one task at a time per worker (OCR is heavy)
    task_acks_late=True,        # ack only after completion — safe retry on crash
    task_reject_on_worker_lost=True,
    # Managed Redis (Upstash) closes idle connections — without these, a stale
    # pooled connection raises straight through .delay() as a 500 instead of
    # transparently reconnecting.
    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,
    broker_pool_limit=None,     # disable pooling — reconnect fresh each publish
    broker_transport_options={
        "socket_keepalive": True,
        "health_check_interval": 30,
    },
    redis_socket_keepalive=True,
)
