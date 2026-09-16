"""Privacy-safe structured logging and Prometheus metrics."""
from __future__ import annotations

import contextvars
import json
import logging
import os
import socket
import time
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from prometheus_client import Counter, Gauge, Histogram

request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
session_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar("session_id", default=None)

SENSITIVE_KEYS = {"prompt", "response", "content", "text", "document", "raw_text", "authorization", "token", "api_key", "secret", "password"}

def new_request_id() -> str:
    return str(uuid.uuid4())

def _safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: "[REDACTED]" if k.lower() in SENSITIVE_KEYS else _safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "environment": os.getenv("APP_ENV", "development"),
            "service": os.getenv("SERVICE_NAME", "legal-assist-api"),
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
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)

def configure_logging() -> None:
    root = logging.getLogger()
    root.setLevel(os.getenv("LOG_LEVEL", "INFO").upper())
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root.handlers.clear()
    root.addHandler(handler)


def log_event(logger: logging.Logger, level: int, event: str, message: str = "", **fields: Any) -> None:
    logger.log(level, message or event, extra={"event": event, "fields": fields})

@contextmanager
def observe(histogram: Histogram, **labels: str) -> Iterator[None]:
    start = time.perf_counter()
    try:
        yield
    finally:
        histogram.labels(**labels).observe(time.perf_counter() - start)

llm_calls_total = Counter("legal_assist_llm_calls_total", "LLM calls", ["provider", "purpose", "outcome"])
llm_call_duration_seconds = Histogram("legal_assist_llm_call_duration_seconds", "LLM latency", ["provider", "purpose"])
llm_fallback_total = Counter("legal_assist_llm_fallback_total", "LLM fallbacks", ["from_provider", "to_provider", "purpose"])
ocr_duration_seconds = Histogram("legal_assist_ocr_duration_seconds", "OCR latency", ["mode"])
pii_entities_redacted_total = Counter("legal_assist_pii_entities_redacted_total", "Redacted PII entities", ["entity_type"])
htoc_build_duration_seconds = Histogram("legal_assist_htoc_build_duration_seconds", "HTOC build latency", ["provider"])
bm25_query_duration_seconds = Histogram("legal_assist_bm25_query_duration_seconds", "BM25 latency")
celery_tasks_total = Counter("legal_assist_celery_tasks_total", "Celery tasks", ["task_name", "status"])
celery_task_duration_seconds = Histogram("legal_assist_celery_task_duration_seconds", "Celery task latency", ["task_name"])
celery_queue_waiting = Gauge("legal_assist_celery_queue_waiting_tasks", "Waiting Celery tasks")
celery_oldest_task_age_seconds = Gauge("legal_assist_celery_oldest_task_age_seconds", "Age of oldest waiting task")
worker_heartbeat_age_seconds = Gauge("legal_assist_worker_heartbeat_age_seconds", "Worker heartbeat age")
active_sessions = Gauge("legal_assist_active_sessions", "Active sessions")
sessions_expired_total = Counter("legal_assist_sessions_expired_total", "Expired sessions")
