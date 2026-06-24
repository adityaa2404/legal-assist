import asyncio
import logging
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


def _run(coro):
    """Run an async coroutine from a sync Celery task."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


@shared_task(
    bind=True,
    name="tasks.process_document",
    max_retries=2,
    default_retry_delay=30,
)
def process_document(
    self,
    session_id: str,
    content_b64: str,
    content_type: str,
    doc_type: str,
    ocr_language: str,
    ocr_mode: str,
    ai_provider: str,
):
    """
    Celery task: full document processing pipeline.
    Replaces asyncio.create_task(_process_document_background(...)).
    content is base64-encoded because Celery serializes args as JSON.
    """
    import base64
    from app.services.pii_anonymizer import PIIAnonymizer
    from app.services.gemini_client import GeminiClient
    from app.services.htoc_builder import HTOCBuilder
    from app.services.session_service import SessionService
    from app.api.v1.documents import _process_document_inner

    content = base64.b64decode(content_b64)

    pii_service = PIIAnonymizer()
    gemini = GeminiClient()
    htoc_builder = HTOCBuilder()
    session_service = SessionService()

    try:
        _run(
            _process_document_inner(
                session_id=session_id,
                content=content,
                content_type=content_type,
                doc_type=doc_type,
                ocr_language=ocr_language,
                pii_service=pii_service,
                gemini=gemini,
                htoc_builder=htoc_builder,
                session_service=session_service,
                ocr_mode=ocr_mode,
                ai_provider=ai_provider,
            )
        )
    except SoftTimeLimitExceeded:
        logger.error("Soft time limit exceeded for session %s", session_id)
        _run(session_service.set_htoc_status(session_id, "failed"))
    except Exception as exc:
        logger.error("Task failed for session %s: %s", session_id, exc)
        _run(session_service.set_htoc_status(session_id, "failed"))
        raise self.retry(exc=exc)


@shared_task(
    bind=True,
    name="tasks.build_htoc_bm25",
    max_retries=2,
    default_retry_delay=30,
)
def build_htoc_bm25(
    self,
    session_id: str,
    anonymized_pages: list,
    ai_provider: str,
    page_chunks: list,
):
    """
    Celery task: HTOC + BM25 only (small digital docs where PII is already done inline).
    Replaces asyncio.create_task(_build_htoc_and_bm25(...)).
    """
    from app.services.gemini_client import GeminiClient
    from app.services.htoc_builder import HTOCBuilder
    from app.services.session_service import SessionService
    from app.api.v1.documents import _build_htoc_and_bm25

    gemini = GeminiClient()
    htoc_builder = HTOCBuilder()
    session_service = SessionService()

    try:
        _run(
            _build_htoc_and_bm25(
                session_id=session_id,
                anonymized_pages=anonymized_pages,
                gemini=gemini,
                htoc_builder=htoc_builder,
                session_service=session_service,
                ai_provider=ai_provider,
                page_chunks=page_chunks,
            )
        )
    except SoftTimeLimitExceeded:
        logger.error("Soft time limit exceeded building HTOC for session %s", session_id)
        _run(session_service.set_htoc_status(session_id, "failed"))
    except Exception as exc:
        logger.error("HTOC/BM25 task failed for session %s: %s", session_id, exc)
        _run(session_service.set_htoc_status(session_id, "failed"))
        raise self.retry(exc=exc)
