"""Propagate request/session correlation IDs across Celery boundaries."""

from __future__ import annotations

import logging

from celery.signals import before_task_publish, task_postrun, task_prerun

from app.core.observability import request_id_ctx, session_id_ctx

logger = logging.getLogger(__name__)
_task_context_tokens = {}


@before_task_publish.connect(weak=False)
def _propagate_context(sender=None, headers=None, **kwargs):
    """Copy HTTP correlation IDs into Celery task headers."""
    if headers is None:
        return

    request_id = request_id_ctx.get()
    session_id = session_id_ctx.get()

    if request_id:
        headers["legal_assist_request_id"] = request_id
    if session_id:
        headers["legal_assist_session_id"] = session_id


@task_prerun.connect(weak=False)
def _restore_context(task_id=None, task=None, **kwargs):
    """Restore correlation IDs inside the worker task execution context."""
    headers = getattr(getattr(task, "request", None), "headers", None) or {}
    request_id = headers.get("legal_assist_request_id")
    session_id = headers.get("legal_assist_session_id")

    request_token = request_id_ctx.set(request_id)
    session_token = session_id_ctx.set(session_id)
    _task_context_tokens[str(task_id)] = (request_token, session_token)


@task_postrun.connect(weak=False)
def _clear_context(task_id=None, **kwargs):
    tokens = _task_context_tokens.pop(str(task_id), None)
    if not tokens:
        return

    request_token, session_token = tokens
    session_id_ctx.reset(session_token)
    request_id_ctx.reset(request_token)
