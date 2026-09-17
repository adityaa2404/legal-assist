"""Direct instrumentation for the core Legal Assist service paths.

This module makes the core LLM, OCR, and PII metrics independent of the
runtime monkey-patching layer. It also enforces the application's current
Gemini-only policy for all instrumented service calls and disables non-Gemini
fallback helpers so metrics cannot report a fallback result as Gemini success.
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


def _call_gemini_only(
    fn: Callable[..., Any],
    self_obj: Any,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> Any:
    """Call a provider-aware method with provider forcibly set to Gemini."""
    signature = inspect.signature(fn)
    bound = signature.bind(self_obj, *args, **kwargs)
    if "provider" in signature.parameters:
        bound.arguments["provider"] = "gemini"
    return fn(*bound.args, **bound.kwargs)


def _mark_instrumented(fn: Callable[..., Any]) -> Callable[..., Any]:
    fn._legal_assist_observability_wrapped = True
    return fn


def _build_instrumented_gemini_client(base_cls: type) -> type:
    class InstrumentedGeminiClient(base_cls):
        async def analyze_document(self, *args, **kwargs):
            original = _raw_method(base_cls, "analyze_document")
            started = time.perf_counter()
            try:
                result = await _call_gemini_only(original, self, args, kwargs)
                llm_calls_total.labels(
                    provider="gemini", purpose="analysis", outcome="success"
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="analysis", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="analysis"
                ).observe(time.perf_counter() - started)

        async def generate_json(self, *args, **kwargs):
            original = _raw_method(base_cls, "generate_json")
            started = time.perf_counter()
            try:
                result = await _call_gemini_only(original, self, args, kwargs)
                llm_calls_total.labels(
                    provider="gemini", purpose="generate_json", outcome="success"
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="generate_json", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="generate_json"
                ).observe(time.perf_counter() - started)

        async def chat(self, *args, **kwargs):
            original = _raw_method(base_cls, "chat")
            started = time.perf_counter()
            try:
                result = await _call_gemini_only(original, self, args, kwargs)
                llm_calls_total.labels(
                    provider="gemini", purpose="chat", outcome="success"
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="chat", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="chat"
                ).observe(time.perf_counter() - started)

        async def chat_with_context(self, *args, **kwargs):
            original = _raw_method(base_cls, "chat_with_context")
            started = time.perf_counter()
            try:
                result = await _call_gemini_only(original, self, args, kwargs)
                llm_calls_total.labels(
                    provider="gemini", purpose="chat_with_context", outcome="success"
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="chat_with_context", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="chat_with_context"
                ).observe(time.perf_counter() - started)

        async def ocr_page_image(self, *args, **kwargs):
            original = _raw_method(base_cls, "ocr_page_image")
            started = time.perf_counter()
            try:
                result = await original(self, *args, **kwargs)
                llm_calls_total.labels(
                    provider="gemini", purpose="ocr", outcome="success"
                ).inc()
                return result
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="ocr", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="ocr"
                ).observe(time.perf_counter() - started)

        async def chat_stream(self, *args, **kwargs):
            original = _raw_method(base_cls, "chat_stream")
            started = time.perf_counter()
            try:
                stream = _call_gemini_only(original, self, args, kwargs)
                async for chunk in stream:
                    yield chunk
                llm_calls_total.labels(
                    provider="gemini", purpose="chat_stream", outcome="success"
                ).inc()
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="chat_stream", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="chat_stream"
                ).observe(time.perf_counter() - started)

        async def chat_with_context_stream(self, *args, **kwargs):
            original = _raw_method(base_cls, "chat_with_context_stream")
            started = time.perf_counter()
            try:
                stream = _call_gemini_only(original, self, args, kwargs)
                async for chunk in stream:
                    yield chunk
                llm_calls_total.labels(
                    provider="gemini", purpose="chat_with_context_stream", outcome="success"
                ).inc()
            except Exception:
                llm_calls_total.labels(
                    provider="gemini", purpose="chat_with_context_stream", outcome="error"
                ).inc()
                raise
            finally:
                llm_call_duration_seconds.labels(
                    provider="gemini", purpose="chat_with_context_stream"
                ).observe(time.perf_counter() - started)

    InstrumentedGeminiClient.__name__ = base_cls.__name__
    InstrumentedGeminiClient.__qualname__ = base_cls.__qualname__

    for name in (
        "analyze_document",
        "generate_json",
        "chat",
        "chat_with_context",
        "ocr_page_image",
        "chat_stream",
        "chat_with_context_stream",
    ):
        if hasattr(InstrumentedGeminiClient, name):
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


def _disable_non_gemini_helpers(gemini_module: Any) -> None:
    """Disable non-Gemini backends so fallback/provider drift is impossible."""
    def _disabled(*_args, **_kwargs):
        raise RuntimeError("Gemini-only mode: non-Gemini provider disabled")

    for name in (
        "_groq_generate_json_sync",
        "_groq_chat_sync",
        "_openai_generate_json_sync",
        "_openai_chat_sync",
        "_claude_generate_json_sync",
        "_claude_chat_sync",
    ):
        if hasattr(gemini_module, name):
            setattr(gemini_module, name, _disabled)


def install_direct_observability() -> None:
    """Replace service exports before API/Celery paths create instances."""
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
    _disable_non_gemini_helpers(gemini_module)

    # Patch already-imported bindings as well as future imports.
    bindings = (
        ("app.api.v1.documents", "GeminiClient"),
        ("app.api.v1.documents", "DocumentParser"),
        ("app.api.v1.documents", "PIIAnonymizer"),
        ("app.api.v1.chat", "GeminiClient"),
        ("app.api.v1.chat", "PIIAnonymizer"),
        ("app.api.v1.analysis", "GeminiClient"),
        ("app.api.v1.analysis", "PIIAnonymizer"),
        ("app.core.dependencies", "GeminiClient"),
        ("app.core.dependencies", "DocumentParser"),
        ("app.core.dependencies", "PIIAnonymizer"),
    )
    replacements = {
        "GeminiClient": instrumented_gemini,
        "DocumentParser": instrumented_parser,
        "PIIAnonymizer": instrumented_pii,
    }
    for module_name, class_name in bindings:
        _replace_binding(module_name, class_name, replacements[class_name])


install_direct_observability()
