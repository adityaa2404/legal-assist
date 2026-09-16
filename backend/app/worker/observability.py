from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Any

from celery.signals import (
    heartbeat_sent,
    task_failure,
    task_postrun,
    task_prerun,
    task_retry,
    worker_ready,
)

from app.core.observability import (
    celery_task_duration_seconds,
    celery_tasks_total,
    celery_worker_heartbeat_age_seconds,
    log_event,
)

logger = logging.getLogger(__name__)

_task_started_at: dict[str, float] = {}
_task_started_lock = threading.Lock()
_last_heartbeat_monotonic: float | None = None


def _task_name(task: Any) -> str:
    return getattr(task, "name", "unknown") or "unknown"


def _record_task_finished(task_id: str | None, task_name: str, status: str) -> None:
    now = time.monotonic()
    started_at = None

    if task_id:
        with _task_started_lock:
            started_at = _task_started_at.pop(task_id, None)

    if started_at is not None:
        celery_task_duration_seconds.labels(task_name=task_name).observe(
            max(0.0, now - started_at)
        )

    celery_tasks_total.labels(task_name=task_name, status=status).inc()


def _on_task_prerun(task_id=None, task=None, **kwargs):
    task_name = _task_name(task)
    if task_id:
        with _task_started_lock:
            _task_started_at[task_id] = time.monotonic()

    log_event(
        logging.INFO,
        "celery_task_started",
        task_name=task_name,
        task_id=task_id,
    )


@task_postrun.connect(weak=False)
def _on_task_postrun(task_id=None, task=None, state=None, **kwargs):
    _record_task_finished(
        task_id,
        _task_name(task),
        "success" if state == "SUCCESS" else (state or "unknown").lower(),
    )

    log_event(
        logging.INFO,
        "celery_task_finished",
        task_name=_task_name(task),
        task_id=task_id,
        status=state or "unknown",
    )


@task_failure.connect(weak=False)
def _on_task_failure(task_id=None, task=None, exception=None, **kwargs):
    _record_task_finished(task_id, _task_name(task), "failure")

    log_event(
        logging.ERROR,
        "celery_task_failed",
        task_name=_task_name(task),
        task_id=task_id,
        exception_type=type(exception).__name__ if exception else None,
    )


@task_retry.connect(weak=False)
def _on_task_retry(request=None, reason=None, **kwargs):
    task_name = getattr(request, "task", "unknown") if request else "unknown"
    task_id = getattr(request, "id", None) if request else None

    _record_task_finished(task_id, task_name, "retry")

    log_event(
        logging.WARNING,
        "celery_task_retry",
        task_name=task_name,
        task_id=task_id,
        reason_type=type(reason).__name__ if reason else None,
    )


@heartbeat_sent.connect(weak=False)
def _on_heartbeat_sent(**kwargs):
    global _last_heartbeat_monotonic
    _last_heartbeat_monotonic = time.monotonic()


def heartbeat_age_seconds() -> float:
    if _last_heartbeat_monotonic is None:
        return 0.0
    return max(0.0, time.monotonic() - _last_heartbeat_monotonic)


def _heartbeat_refresh_loop() -> None:
    while True:
        celery_worker_heartbeat_age_seconds.set(heartbeat_age_seconds())
        time.sleep(5)


@worker_ready.connect(weak=False)
def _on_worker_ready(sender=None, **kwargs):
    log_event(
        logging.INFO,
        "celery_worker_ready",
        worker=getattr(sender, "hostname", None),
    )

    threading.Thread(
        target=_heartbeat_refresh_loop,
        daemon=True,
        name="worker-heartbeat-metrics",
    ).start()


# Keep the module import side-effect based: importing it registers Celery signals.
__all__ = ["heartbeat_age_seconds"]
