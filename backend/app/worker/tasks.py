import asyncio
import logging
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded

logger = logging.getLogger(__name__)


_worker_loop: asyncio.AbstractEventLoop | None = None


def _run(coro):
    """
    Run an async coroutine from a sync Celery task.

    Reuses one event loop for the lifetime of the worker process instead of
    creating/closing a loop per task. Async singletons with loop-bound internals
    (e.g. Motor's AsyncIOMotorClient in app.core.database) are created lazily on
    first use and stay attached to whichever loop was running at that point —
    closing that loop after every task would leave those singletons permanently
    broken ("RuntimeError: Event loop is closed") for the rest of the process.
    """
    global _worker_loop
    if _worker_loop is None or _worker_loop.is_closed():
        _worker_loop = asyncio.new_event_loop()
    asyncio.set_event_loop(_worker_loop)
    return _worker_loop.run_until_complete(coro)


@shared_task(
    bind=True,
    name="tasks.process_document",
    max_retries=2,
    default_retry_delay=30,
)
def process_document(
    self,
    session_id: str,
    content_type: str,
    doc_type: str,
    ocr_language: str,
    ocr_mode: str,
    ai_provider: str,
):
    """
    Celery task: full document processing pipeline.
    Replaces asyncio.create_task(_process_document_background(...)).

    File bytes are fetched from MongoDB (document_files, keyed by session_id)
    rather than passed through the task message: managed Redis (e.g. Upstash)
    hard-rejects single requests above ~8-10MB, and embedding a whole PDF as
    base64 in the Celery message body silently exceeds that on any file above
    a few MB, crashing the publish before the task is even enqueued.
    """
    from app.services.pii_anonymizer import PIIAnonymizer
    from app.services.gemini_client import GeminiClient
    from app.services.htoc_builder import HTOCBuilder
    from app.services.session_service import SessionService
    from app.core.database import get_database
    from app.api.v1.documents import _process_document_inner

    async def _fetch_content() -> bytes:
        db = get_database()
        doc = await db.document_files.find_one({"session_id": session_id})
        if not doc:
            raise ValueError(f"No stored file found for session {session_id}")
        return bytes(doc["pdf_bytes"])

    content = _run(_fetch_content())

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


async def _build_report(session_id: str, report_type: str) -> bytes:
    """
    Run/fetch the cached analysis, then render it to PDF. Kept out of the API
    request path — WeasyPrint's HTML->PDF render is CPU-bound enough to stall
    the async event loop for every other concurrent request on that API
    process while it runs.
    """
    from app.services.pii_anonymizer import PIIAnonymizer
    from app.services.gemini_client import GeminiClient
    from app.services.tree_search import TreeSearchService
    from app.services.session_service import SessionService
    from app.services.report_generator import create_pdf_from_analysis
    from app.api.v1.analysis import _get_or_run_analysis

    session_service = SessionService()
    session = await session_service.get(session_id)
    if not session:
        raise ValueError(f"Session {session_id} not found")

    result = await _get_or_run_analysis(
        session_id, report_type, session_service,
        PIIAnonymizer(), GeminiClient(), TreeSearchService(),
    )
    filename = (session.document_metadata or {}).get("filename", "document")
    return create_pdf_from_analysis(result, filename, report_type)


@shared_task(
    bind=True,
    name="tasks.generate_report",
)
def generate_report(self, session_id: str, report_type: str):
    """Build the analysis PDF report and cache it on the session (report_pdf.{type})."""
    from app.services.session_service import SessionService

    session_service = SessionService()

    async def _run_and_save():
        pdf_bytes = await _build_report(session_id, report_type)
        await session_service.save_report(session_id, report_type, pdf_bytes)

    try:
        _run(_run_and_save())
    except SoftTimeLimitExceeded:
        logger.error("Soft time limit exceeded generating report for session %s", session_id)
        _run(session_service.set_report_status(session_id, report_type, "failed"))
    except Exception as exc:
        # A rendering error must be terminal for this report. Retrying a missing
        # native WeasyPrint dependency or a malformed template only repeats the
        # same failure and can destabilize the limited worker container.
        logger.exception("Report generation failed for session %s", session_id)
        _run(session_service.set_report_status(session_id, report_type, "failed"))
        return {"status": "failed", "error": str(exc)}
