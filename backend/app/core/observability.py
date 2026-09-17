"""Privacy-safe structured logging and Prometheus metrics."""

from __future__ import annotations

import contextvars
import json
import logging
import os
import socket
import threading
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

import redis
from celery.signals import (
    before_task_publish,
    heartbeat_sent,
    task_postrun,
    task_prerun,
    worker_ready,
)
from prometheus_client import Counter, Gauge, Histogram

from app.core.config import settings


# ---------------------------------------------------------------------------
# Request/session correlation
# ---------------------------------------------------------------------------

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "request_id",
    default=None,
)

session_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "session_id",
    default=None,
)


# ---------------------------------------------------------------------------
# Privacy-safe logging
# ---------------------------------------------------------------------------

SENSITIVE_KEYS = {
    "prompt",
    "response",
    "content",
    "text",
    "document",
    "document_text",
    "raw_text",
    "authorization",
    "token",
    "api_key",
    "secret",
    "password",
}


def new_request_id() -> str:
    return str(uuid.uuid4())


def _safe(value: Any) -> Any:
    """
    Recursively redact sensitive dictionary values before logging.
    """

    if isinstance(value, dict):
        return {
            key: (
                "[REDACTED]"
                if str(key).lower() in SENSITIVE_KEYS
                else _safe(item)
            )
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [_safe(item) for item in value]

    return value


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(
                record,
                "%Y-%m-%dT%H:%M:%S%z",
            ),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": os.getenv(
                "APP_ENV",
                "development",
            ),
            "service": os.getenv(
                "SERVICE_NAME",
                "legal-assist-api",
            ),
            "request_id": request_id_ctx.get(),
            "session_id": session_id_ctx.get(),
            "host": socket.gethostname(),
        }

        event = getattr(record, "event", None)

        if event:
            payload["event"] = event

        fields = getattr(record, "fields", None)

        if fields:
            payload.update(_safe(fields))

        if record.exc_info:
            payload["exception"] = self.formatException(
                record.exc_info
            )

        return json.dumps(
            payload,
            default=str,
            ensure_ascii=False,
        )


def configure_logging() -> None:
    root = logging.getLogger()

    root.setLevel(
        os.getenv(
            "LOG_LEVEL",
            "INFO",
        ).upper()
    )

    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())

    root.handlers.clear()
    root.addHandler(handler)


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str = "",
    **fields: Any,
) -> None:
    logger.log(
        level,
        message or event,
        extra={
            "event": event,
            "fields": fields,
        },
    )


@contextmanager
def observe(
    histogram: Histogram,
    **labels: str,
) -> Iterator[None]:
    start = time.perf_counter()

    try:
        yield

    finally:
        histogram.labels(**labels).observe(
            time.perf_counter() - start
        )


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------

llm_calls_total = Counter(
    "legal_assist_llm_calls_total",
    "LLM calls",
    ["provider", "purpose", "outcome"],
)

llm_call_duration_seconds = Histogram(
    "legal_assist_llm_call_duration_seconds",
    "LLM latency",
    ["provider", "purpose"],
)

llm_fallback_total = Counter(
    "legal_assist_llm_fallback_total",
    "LLM fallbacks",
    ["from_provider", "to_provider", "purpose"],
)

ocr_duration_seconds = Histogram(
    "legal_assist_ocr_duration_seconds",
    "OCR latency",
    ["mode"],
)

pii_entities_redacted_total = Counter(
    "legal_assist_pii_entities_redacted_total",
    "Redacted PII entities",
    ["entity_type"],
)

htoc_build_duration_seconds = Histogram(
    "legal_assist_htoc_build_duration_seconds",
    "HTOC build latency",
    ["provider"],
)

bm25_query_duration_seconds = Histogram(
    "legal_assist_bm25_query_duration_seconds",
    "BM25 latency",
)

# ---------------------------------------------------------------------------
# Celery metrics
#
# These are safe for Prometheus multiprocess mode.
# ---------------------------------------------------------------------------

celery_tasks_total = Counter(
    "legal_assist_celery_tasks_total",
    "Celery tasks",
    ["task_name", "status"],
)

celery_task_duration_seconds = Histogram(
    "legal_assist_celery_task_duration_seconds",
    "Celery task latency",
    ["task_name"],
)

celery_queue_waiting = Gauge(
    "legal_assist_celery_queue_waiting_tasks",
    "Waiting Celery tasks",
    multiprocess_mode="max",
)

celery_oldest_task_age_seconds = Gauge(
    "legal_assist_celery_oldest_task_age_seconds",
    "Age of oldest waiting task",
    multiprocess_mode="max",
)

worker_heartbeat_age_seconds = Gauge(
    "legal_assist_worker_heartbeat_age_seconds",
    "Worker heartbeat age",
    multiprocess_mode="max",
)

active_sessions = Gauge(
    "legal_assist_active_sessions",
    "Active sessions",
    multiprocess_mode="max",
)

sessions_expired_total = Counter(
    "legal_assist_sessions_expired_total",
    "Expired sessions",
)


# ---------------------------------------------------------------------------
# Celery queue tracking
# ---------------------------------------------------------------------------

_QUEUE_TRACKING_KEY = "legal_assist:celery:task_enqueue_times"

_QUEUE_TRACKING_MAX_AGE_SECONDS = 7 * 24 * 60 * 60

_task_start_times: dict[str, float] = {}

_last_heartbeat_at = time.time()

_queue_metrics_thread_started = False
_heartbeat_metrics_thread_started = False


_redis_client: redis.Redis | None = None


def _get_redis_client() -> redis.Redis:
    """
    Lazily create a Redis client.

    Observability failures must never break application functionality.
    """

    global _redis_client

    if _redis_client is None:
        _redis_client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=False,
        )

    return _redis_client


# ---------------------------------------------------------------------------
# Celery publish tracking
# ---------------------------------------------------------------------------

@before_task_publish.connect
def _track_task_published(
    sender=None,
    headers=None,
    **kwargs,
):
    """
    Record when a task enters the broker.

    The Redis sorted set lets the worker calculate:
        - queue depth
        - oldest queued task age

    No document/session contents are stored.
    """

    headers = headers or {}

    task_id = (
        headers.get("id")
        or headers.get("task_id")
    )

    if not task_id:
        return

    try:
        client = _get_redis_client()

        client.zadd(
            _QUEUE_TRACKING_KEY,
            {
                str(task_id): time.time(),
            },
        )

    except Exception:
        # Observability must never break task publishing.
        logging.getLogger(__name__).debug(
            "Unable to record Celery enqueue time",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Celery execution metrics
# ---------------------------------------------------------------------------

@task_prerun.connect
def _task_started(
    task_id=None,
    task=None,
    **kwargs,
):
    if not task_id:
        return

    _task_start_times[str(task_id)] = time.perf_counter()

    try:
        _get_redis_client().zrem(
            _QUEUE_TRACKING_KEY,
            str(task_id),
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Unable to remove Celery task from queue tracking",
            exc_info=True,
        )


@task_postrun.connect
def _task_finished(
    task_id=None,
    task=None,
    state=None,
    **kwargs,
):
    if not task_id:
        return

    task_name = getattr(
        task,
        "name",
        "unknown",
    )

    task_id = str(task_id)

    start_time = _task_start_times.pop(
        task_id,
        None,
    )

    status = str(state or "UNKNOWN").lower()

    celery_tasks_total.labels(
        task_name=task_name,
        status=status,
    ).inc()

    if start_time is not None:
        celery_task_duration_seconds.labels(
            task_name=task_name,
        ).observe(
            time.perf_counter() - start_time
        )

    try:
        _get_redis_client().zrem(
            _QUEUE_TRACKING_KEY,
            task_id,
        )
    except Exception:
        logging.getLogger(__name__).debug(
            "Unable to clean up Celery queue tracking",
            exc_info=True,
        )


# ---------------------------------------------------------------------------
# Worker heartbeat
# ---------------------------------------------------------------------------

@heartbeat_sent.connect
def _heartbeat_received(
    sender=None,
    **kwargs,
):
    global _last_heartbeat_at

    _last_heartbeat_at = time.time()


def _heartbeat_metrics_loop() -> None:
    global _last_heartbeat_at

    while True:
        try:
            worker_heartbeat_age_seconds.set(
                max(
                    0.0,
                    time.time() - _last_heartbeat_at,
                )
            )
        except Exception:
            logging.getLogger(__name__).debug(
                "Unable to update worker heartbeat metric",
                exc_info=True,
            )

        time.sleep(5)


# ---------------------------------------------------------------------------
# Queue metrics
# ---------------------------------------------------------------------------

def _queue_metrics_loop() -> None:
    while True:
        try:
            client = _get_redis_client()

            now = time.time()

            # Remove abandoned tracking entries that are older than the
            # maximum observation window.
            client.zremrangebyscore(
                _QUEUE_TRACKING_KEY,
                0,
                now - _QUEUE_TRACKING_MAX_AGE_SECONDS,
            )

            waiting_count = client.zcard(
                _QUEUE_TRACKING_KEY
            )

            celery_queue_waiting.set(
                float(waiting_count)
            )

            oldest = client.zrange(
                _QUEUE_TRACKING_KEY,
                0,
                0,
                withscores=True,
            )

            if oldest:
                oldest_timestamp = float(
                    oldest[0][1]
                )

                celery_oldest_task_age_seconds.set(
                    max(
                        0.0,
                        now - oldest_timestamp,
                    )
                )
            else:
                celery_oldest_task_age_seconds.set(0.0)

        except Exception:
            logging.getLogger(__name__).debug(
                "Unable to update Celery queue metrics",
                exc_info=True,
            )

            celery_queue_waiting.set(0.0)
            celery_oldest_task_age_seconds.set(0.0)

        time.sleep(5)


@worker_ready.connect
def _start_worker_observability(
    sender=None,
    **kwargs,
):
    """
    Start background metric-updater threads once the worker is ready.

    This runs in the Celery worker process rather than the API process.
    """

    global _queue_metrics_thread_started
    global _heartbeat_metrics_thread_started

    if not _heartbeat_metrics_thread_started:
        _heartbeat_metrics_thread_started = True

        threading.Thread(
            target=_heartbeat_metrics_loop,
            daemon=True,
            name="heartbeat-metrics",
        ).start()

    if not _queue_metrics_thread_started:
        _queue_metrics_thread_started = True

        threading.Thread(
            target=_queue_metrics_loop,
            daemon=True,
            name="queue-metrics",
        ).start()