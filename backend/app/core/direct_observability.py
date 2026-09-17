"""Direct instrumentation for the core Legal Assist service paths.

The existing runtime instrumentation is intentionally left in place for
compatibility, but these subclasses make the critical worker/API metrics
independent of runtime method wrapping. They call the real service methods and
emit Prometheus metrics around the actual execution paths.
"""

from __future__ import annotations

import inspect
import sys
import time
from typing import Any, Callable

from app.core.observability import (
    llm_call_duration_seconds,
    llm_calls_total,
    ocr_duration_seconds,
    pii_entities_redacted_total,
)


def _raw_method(cls: type, name: str) -> Callable[..., Any]:
    """Return the original implementation if another layer wrapped it."""
    return inspect.unwrap(getattr(cls, name))


def _provider_from_call(
    fn: Callable[..., Any],
    self_obj: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> str:
    try:
        bound = inspect.signature(fn).bind(self_obj, *args, **kwargs)
        return str(bound.arguments.get("provider", "gemini") or "gemini").lower()
    except Exception:
        return "gemini"


def _mark_instrumented(fn: Callable[..., Any]) -> Callable[..., Any]:
    fn._legal_assist_observability_wrapped = True
    return fn


def _build_instrumented_gemini_client(base_cls: type) -> type:
    class InstrumentedGeminiClient(base_cls):
        async def analyze_document(self, *args, **kwargs):
            original = _raw_method(base_cls, "analyze_document")
            provider = _provider_from_call(original, self, args, kwargs)
            started = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
                llm_calls_total.labels(
                    provider=provider,
                    purpose="analysis",
                    outcome="success",
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider=provider,
                    purpose="analysis",
                    outcome="error",
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider=provider,
                    purpose="analysis",
                ).observe(time.perf_counter() - started)

        async def generate_json(self, *args, **kwargs):
            original = _raw_method(base_cls, "generate_json")
            provider = _provider_from_call(original, self, args, kwargs)
            started = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
                llm_calls_total.labels(
                    provider=provider,
                    purpose="generate_json",
                    outcome="success",
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider=provider,
                    purpose="generate_json",
                    outcome="error",
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider=provider,
                    purpose="generate_json",
                ).observe(time.perf_counter() - started)

        async def chat(self, *args, **kwargs):
            original = _raw_method(base_cls, "chat")
            provider = _provider_from_call(original, self, args, kwargs)
            started = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
                llm_calls_total.labels(
                    provider=provider,
                    purpose="chat",
                    outcome="success",
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider=provider,
                    purpose="chat",
                    outcome="error",
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider=provider,
                    purpose="chat",
                ).observe(time.perf_counter() - started)

        async def chat_with_context(self, *args, **kwargs):
            original = _raw_method(base_cls, "chat_with_context")
            provider = _provider_from_call(original, self, args, kwargs)
            started = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
                llm_calls_total.labels(
                    provider=provider,
                    purpose="chat_with_context",
                    outcome="success",
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider=provider,
                    purpose="chat_with_context",
                    outcome="error",
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider=provider,
                    purpose="chat_with_context",
                ).observe(time.perf_counter() - started)

        async def ocr_page_image(self, *args, **kwargs):
            original = _raw_method(base_cls, "ocr_page_image")
            provider = _provider_from_call(original, self, args, kwargs)
            started = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
                llm_calls_total.labels(
                    provider=provider,
                    purpose="ocr",
                    outcome="success",
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider=provider,
                    purpose="ocr",
                    outcome="error",
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider=provider,
                    purpose="ocr",
                ).observe(time.perf_counter() - started)

    InstrumentedGeminiClient.__name__ = base_cls.__name__
    InstrumentedGeminiClient.__qualname__ = base_cls.__qualname__

    for name in (
        "analyze_document",
        "generate_json",
        "chat",
        "chat_with_context",
        "ocr_page_image",
    ):
        _mark_instrumented(getattr(InstrumentedGeminiClient, name))

    return InstrumentedGeminiClient


def _build_instrumented_parser(base_cls: type) -> type:
    class InstrumentedDocumentParser(base_cls):
        async def _extract_pdf_gemini_vision(self, *args, **kwargs):
            original = _raw_method(base_cls, "_extract_pdf_gemini_vision")
            started = time.perf_counter()
            try:
                return await original(self, *args, **kwargs)
            finally:
                ocr_duration_seconds.labels(mode="fast").observe(
                    time.perf_counter() - started
                )

        async def _extract_pdf_scanned(self, *args, **kwargs):
            original = _raw_method(base_cls, "_extract_pdf_scanned")
            started = time.perf_counter()
            try:
                return await original(self, *args, **kwargs)
            finally:
                ocr_duration_seconds.labels(mode="secure").observe(
                    time.perf_counter() - started
                )

    InstrumentedDocumentParser.__name__ = base_cls.__name__
    InstrumentedDocumentParser.__qualname__ = base_cls.__qualname__
    _mark_instrumented(InstrumentedDocumentParser._extract_pdf_gemini_vision)
    _mark_instrumented(InstrumentedDocumentParser._extract_pdf_scanned)
    return InstrumentedDocumentParser


def _build_instrumented_pii(base_cls: type) -> type:
    class InstrumentedPIIAnonymizer(base_cls):
        def _anonymize_with_presidio(self, *args, **kwargs):
            # Bypass the legacy runtime wrapper so entities are counted once.
            original = _raw_method(base_cls, "_anonymize_with_presidio")
            return original(self, *args, **kwargs)

        async def anonymize(self, *args, **kwargs):
            original = _raw_method(base_cls, "anonymize")
            anonymized_text, mapping = await original(self, *args, **kwargs)

            for token in mapping:
                entity_type = token.strip("[]").rsplit("_", 1)[0] or "UNKNOWN"
                pii_entities_redacted_total.labels(
                    entity_type=entity_type,
                ).inc()

            return anonymized_text, mapping

    InstrumentedPIIAnonymizer.__name__ = base_cls.__name__
    InstrumentedPIIAnonymizer.__qualname__ = base_cls.__qualname__
    _mark_instrumented(InstrumentedPIIAnonymizer._anonymize_with_presidio)
    return InstrumentedPIIAnonymizer


def _replace_binding(module_name: str, class_name: str, replacement: type) -> None:
    module = sys.modules.get(module_name)
    if module is not None:
        setattr(module, class_name, replacement)


def install_direct_observability() -> None:
    """Replace service exports before Celery/API paths create instances."""
    from app.services.gemini_client import GeminiClient
    from app.services.document_parser import DocumentParser
    from app.services.pii_anonymizer import PIIAnonymizer

    instrumented_gemini = _build_instrumented_gemini_client(GeminiClient)
    instrumented_parser = _build_instrumented_parser(DocumentParser)
    instrumented_pii = _build_instrumented_pii(PIIAnonymizer)

    import app.services.gemini_client as gemini_module
    import app.services.document_parser as parser_module
    import app.services.pii_anonymizer as pii_module

    gemini_module.GeminiClient = instrumented_gemini
    parser_module.DocumentParser = instrumented_parser
    pii_module.PIIAnonymizer = instrumented_pii

    # These modules can already be partially imported when celery_app is reached.
    _replace_binding("app.api.v1.documents", "GeminiClient", instrumented_gemini)
    _replace_binding("app.api.v1.documents", "DocumentParser", instrumented_parser)
    _replace_binding("app.api.v1.documents", "PIIAnonymizer", instrumented_pii)

    _replace_binding("app.core.dependencies", "GeminiClient", instrumented_gemini)
    _replace_binding("app.core.dependencies", "DocumentParser", instrumented_parser)
    _replace_binding("app.core.dependencies", "PIIAnonymizer", instrumented_pii)


install_direct_observability()
