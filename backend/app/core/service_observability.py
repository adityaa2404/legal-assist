"""Runtime instrumentation for existing Legal Assist service paths."""

from __future__ import annotations

import contextvars
import functools
import inspect
import logging
import time
from typing import Any, Callable

from celery.signals import worker_ready

from app.core.observability import (
    bm25_query_duration_seconds,
    htoc_build_duration_seconds,
    llm_call_duration_seconds,
    llm_calls_total,
    llm_fallback_total,
    ocr_duration_seconds,
    pii_entities_redacted_total,
)

logger = logging.getLogger(__name__)

_INSTALLED = False
_LOW_LEVEL_SUPPRESSED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "observability_low_level_suppressed", default=False
)
_CURRENT_PROVIDER: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_current_provider", default=None
)
_CURRENT_PURPOSE: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "observability_current_purpose", default=None
)
_FALLBACK_USED: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "observability_fallback_used", default=False
)


def _provider_from_call(fn: Callable[..., Any], self_obj: Any, args: tuple, kwargs: dict) -> str:
    try:
        bound = inspect.signature(fn).bind(self_obj, *args, **kwargs)
        return str(bound.arguments.get("provider", "gemini") or "gemini").lower()
    except Exception:
        return "gemini"


def _install_async_llm_method(cls: type, method_name: str, purpose: str) -> None:
    original = getattr(cls, method_name, None)
    if original is None or getattr(original, "_legal_assist_observability_wrapped", False):
        return

    @functools.wraps(original)
    async def wrapped(self, *args, **kwargs):
        provider = _provider_from_call(original, self, args, kwargs)
        start = time.perf_counter()
        provider_token = _CURRENT_PROVIDER.set(provider)
        purpose_token = _CURRENT_PURPOSE.set(purpose)
        fallback_token = _FALLBACK_USED.set(False)
        suppress_token = _LOW_LEVEL_SUPPRESSED.set(provider != "gemini")
        try:
            result = await original(self, *args, **kwargs)
            outcome = "fallback" if _FALLBACK_USED.get() else "success"
            llm_calls_total.labels(
                provider=provider,
                purpose=purpose,
                outcome=outcome,
            ).inc()
            return result
        except Exception:
            llm_calls_total.labels(
                provider=provider,
                purpose=purpose,
                outcome="error",
            ).inc()
            raise
        finally:
            llm_call_duration_seconds.labels(
                provider=provider,
                purpose=purpose,
            ).observe(time.perf_counter() - start)
            _LOW_LEVEL_SUPPRESSED.reset(suppress_token)
            _FALLBACK_USED.reset(fallback_token)
            _CURRENT_PURPOSE.reset(purpose_token)
            _CURRENT_PROVIDER.reset(provider_token)

    wrapped._legal_assist_observability_wrapped = True
    setattr(cls, method_name, wrapped)


def _install_groq_fallback_hook() -> None:
    import app.services.gemini_client as gemini_module

    original = getattr(gemini_module, "_groq_generate_json_sync", None)
    if original is None or getattr(original, "_legal_assist_observability_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(*args, **kwargs):
        provider = _CURRENT_PROVIDER.get()
        purpose = _CURRENT_PURPOSE.get() or "generate_json"
        is_fallback = (
            provider == "gemini"
            and purpose == "generate_json"
            and not _LOW_LEVEL_SUPPRESSED.get()
        )
        start = time.perf_counter()
        try:
            result = original(*args, **kwargs)
            llm_calls_total.labels(
                provider="groq",
                purpose=purpose,
                outcome="success",
            ).inc()
            if is_fallback:
                _FALLBACK_USED.set(True)
                llm_fallback_total.labels(
                    from_provider="gemini",
                    to_provider="groq",
                    purpose=purpose,
                ).inc()
            return result
        except Exception:
            llm_calls_total.labels(
                provider="groq",
                purpose=purpose,
                outcome="error",
            ).inc()
            if is_fallback:
                _FALLBACK_USED.set(True)
                llm_fallback_total.labels(
                    from_provider="gemini",
                    to_provider="groq",
                    purpose=purpose,
                ).inc()
            raise
        finally:
            llm_call_duration_seconds.labels(
                provider="groq",
                purpose=purpose,
            ).observe(time.perf_counter() - start)

    wrapped._legal_assist_observability_wrapped = True
    gemini_module._groq_generate_json_sync = wrapped


def _install_ocr_metrics() -> None:
    from app.services.document_parser import DocumentParser

    for method_name, mode in (
        ("_extract_pdf_gemini_vision", "fast"),
        ("_extract_pdf_scanned", "secure"),
    ):
        original = getattr(DocumentParser, method_name, None)
        if original is None or getattr(original, "_legal_assist_observability_wrapped", False):
            continue

        @functools.wraps(original)
        async def wrapped(self, *args, __original=original, __mode=mode, **kwargs):
            start = time.perf_counter()
            try:
                return await __original(self, *args, **kwargs)
            finally:
                ocr_duration_seconds.labels(mode=__mode).observe(
                    time.perf_counter() - start
                )

        wrapped._legal_assist_observability_wrapped = True
        setattr(DocumentParser, method_name, wrapped)


def _install_pii_metrics() -> None:
    from app.services.pii_anonymizer import PIIAnonymizer

    original = getattr(PIIAnonymizer, "_anonymize_with_presidio", None)
    if original is None or getattr(original, "_legal_assist_observability_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(self, *args, **kwargs):
        anonymized_text, mapping = original(self, *args, **kwargs)
        for token in mapping:
            entity_type = token.strip("[]").rsplit("_", 1)[0] or "UNKNOWN"
            pii_entities_redacted_total.labels(entity_type=entity_type).inc()
        return anonymized_text, mapping

    wrapped._legal_assist_observability_wrapped = True
    PIIAnonymizer._anonymize_with_presidio = wrapped


def _install_htoc_metrics() -> None:
    from app.services.htoc_builder import HTOCBuilder

    original = getattr(HTOCBuilder, "build_tree", None)
    if original is None or getattr(original, "_legal_assist_observability_wrapped", False):
        return

    @functools.wraps(original)
    async def wrapped(self, *args, **kwargs):
        provider = _provider_from_call(original, self, args, kwargs)
        try:
            bound = inspect.signature(original).bind(self, *args, **kwargs)
            page_texts = bound.arguments.get("page_texts") or []
            if len(page_texts) <= 3:
                provider = "skipped"
            elif len(page_texts) > 50 and provider != "groq":
                provider = "groq"
        except Exception:
            pass
        start = time.perf_counter()
        try:
            return await original(self, *args, **kwargs)
        finally:
            htoc_build_duration_seconds.labels(provider=provider).observe(
                time.perf_counter() - start
            )

    wrapped._legal_assist_observability_wrapped = True
    HTOCBuilder.build_tree = wrapped


def _install_bm25_metrics() -> None:
    from app.services.bm25_search import BM25SearchService

    original = getattr(BM25SearchService, "search", None)
    if original is None or getattr(original, "_legal_assist_observability_wrapped", False):
        return

    @functools.wraps(original)
    def wrapped(self, *args, **kwargs):
        start = time.perf_counter()
        try:
            return original(self, *args, **kwargs)
        finally:
            bm25_query_duration_seconds.observe(time.perf_counter() - start)

    wrapped._legal_assist_observability_wrapped = True
    BM25SearchService.search = wrapped


def install_service_instrumentation() -> None:
    """Install all custom metrics around existing service execution paths."""
    global _INSTALLED
    if _INSTALLED:
        return

    try:
        from app.services.gemini_client import GeminiClient

        _install_async_llm_method(GeminiClient, "analyze_document", "analysis")
        _install_async_llm_method(GeminiClient, "chat", "chat")
        _install_async_llm_method(GeminiClient, "chat_with_context", "chat_with_context")
        _install_async_llm_method(GeminiClient, "generate_json", "generate_json")
        _install_async_llm_method(GeminiClient, "ocr_page_image", "ocr")
        _install_groq_fallback_hook()
        _install_ocr_metrics()
        _install_pii_metrics()
        _install_htoc_metrics()
        _install_bm25_metrics()
        _INSTALLED = True
        logger.info("service observability instrumentation installed")
    except Exception:
        logger.exception("Failed to install service observability instrumentation")
        # Observability must never prevent API/worker startup.


@worker_ready.connect(weak=False)
def _install_worker_observability(**kwargs):
    install_service_instrumentation()
