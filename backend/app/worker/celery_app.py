from celery import Celery

from app.core.config import settings

# Importing this module registers the Celery observability signal handlers:
# - before_task_publish
# - task_prerun
# - task_postrun
# - heartbeat_sent
# - worker_ready
from app.core import observability  # noqa: F401
from app.core import task_correlation  # noqa: F401
from app.core import service_observability  # noqa: F401
from app.core import direct_observability  # noqa: F401


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

    task_time_limit=900,
    task_soft_time_limit=780,

    worker_prefetch_multiplier=1,

    task_acks_late=True,
    task_reject_on_worker_lost=True,

    broker_connection_retry_on_startup=True,
    broker_connection_retry=True,
    broker_connection_max_retries=10,

    broker_pool_limit=None,

    broker_transport_options={
        "socket_keepalive": True,
        "health_check_interval": 30,
        "polling_interval": 30,
    },

    redis_socket_keepalive=True,
)
