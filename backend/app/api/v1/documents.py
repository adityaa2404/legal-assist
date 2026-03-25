from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header, Query
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.document_parser import DocumentParser
from app.services.session_service import SessionService
from app.services.gemini_client import GeminiClient
from app.services.htoc_builder import HTOCBuilder
from app.services.bm25_search import BM25SearchService
from app.core.dependencies import (
    get_pii_service, get_parser, get_session_service,
    get_current_user, get_gemini_client, get_htoc_builder,
)
from app.core.config import settings
from pydantic import BaseModel
from typing import Optional
import asyncio
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Unique separator that won't appear in legal documents
PAGE_SEPARATOR = "\n\n<<<<<PAGE_BOUNDARY>>>>>\n\n"


class UploadResponse(BaseModel):
    session_id: str
    filename: str
    page_count: int
    detected_pii_count: int
    needs_ocr: bool
    expires_in_seconds: int
    htoc_status: str  # "building" | "processing" | "ready" | "failed"


ALLOWED_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword"
]


async def _process_document_background(
    session_id: str,
    content: bytes,
    content_type: str,
    doc_type: str,
    ocr_language: str,
    pii_service: PIIAnonymizer,
    gemini: GeminiClient,
    htoc_builder: HTOCBuilder,
    session_service: SessionService,
):
    """
    Background task for scanned docs: OCR → PII → HTOC + BM25.
    For digital docs, only HTOC + BM25 runs here (OCR not needed).
    """
    try:
        await session_service.set_htoc_status(session_id, "processing")

        # Step 1: OCR (only for scanned docs)
        parser = DocumentParser()
        await parser.extract_async(content, content_type, doc_type, ocr_language)
        raw_page_texts = parser.page_texts

        if not raw_page_texts or not any(t.strip() for t in raw_page_texts):
            await session_service.set_htoc_status(session_id, "failed")
            logger.error(f"OCR returned no text for session {session_id}")
            return

        # Step 2: PII anonymization
        joined_with_separators = PAGE_SEPARATOR.join(raw_page_texts)
        anonymized_joined, pii_mapping = await pii_service.anonymize(joined_with_separators)
        anonymized_pages = anonymized_joined.split(PAGE_SEPARATOR)
        anonymized_text = "\n\n".join(anonymized_pages)

        # Step 3: Update session with extracted text + PII mapping
        await session_service.collection.update_one(
            {"session_id": session_id},
            {"$set": {
                "anonymized_text": anonymized_text,
                "page_texts": anonymized_pages,
                "pii_mapping": pii_mapping,
                "htoc_status": "building",
                "document_metadata.page_count": parser.page_count,
            }}
        )
        logger.info(f"OCR + PII done for session {session_id}, {len(anonymized_pages)} pages")

        # Step 4: Build HTOC + BM25
        await _build_htoc_and_bm25(session_id, anonymized_pages, gemini, htoc_builder, session_service)

    except Exception as e:
        logger.error(f"Background processing failed for {session_id}: {e}")
        await session_service.set_htoc_status(session_id, "failed")


async def _build_htoc_and_bm25(
    session_id: str,
    anonymized_pages: list,
    gemini: GeminiClient,
    htoc_builder: HTOCBuilder,
    session_service: SessionService,
):
    """Build HTOC tree + BM25 index, then update session."""
    try:
        # Build HTOC tree (parallel chunk building inside)
        htoc_tree = await htoc_builder.build_tree(anonymized_pages, gemini)
        node_count = _count_nodes(htoc_tree)
        logger.info(f"HTOC tree built with {node_count} sections for session {session_id}")

        # Build BM25 index from pages + HTOC metadata
        bm25 = BM25SearchService()
        bm25.build_index(anonymized_pages, htoc_tree)
        bm25_data = bm25.get_serializable_data()

        # Save both to session
        await session_service.update_htoc_and_bm25(
            session_id, htoc_tree, bm25_data, status="ready"
        )
        logger.info(f"HTOC + BM25 ready for session {session_id}")

    except Exception as e:
        logger.error(f"HTOC build failed for {session_id}: {e}")
        # Still build BM25 index without HTOC (keyword-only, still useful)
        try:
            bm25 = BM25SearchService()
            bm25.build_index(anonymized_pages, None)
            bm25_data = bm25.get_serializable_data()
            await session_service.update_htoc_and_bm25(
                session_id, None, bm25_data, status="failed"
            )
            logger.info(f"BM25-only index saved for {session_id} (HTOC failed)")
        except Exception as e2:
            logger.error(f"BM25 fallback also failed: {e2}")
            await session_service.set_htoc_status(session_id, "failed")


@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(default="digital"),
    ocr_language: str = Form(default="en-IN"),
    current_user: str = Depends(get_current_user),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    parser: DocumentParser = Depends(get_parser),
    session_service: SessionService = Depends(get_session_service),
    gemini: GeminiClient = Depends(get_gemini_client),
    htoc_builder: HTOCBuilder = Depends(get_htoc_builder),
):
    # 1. Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only PDF and DOCX supported")

    if doc_type not in ("digital", "scanned"):
        raise HTTPException(400, "doc_type must be 'digital' or 'scanned'")

    # 2. Read file into memory (never touches disk)
    content = await file.read()

    if doc_type == "scanned":
        # ── SCANNED PATH: everything runs in background ──
        # Get page count quickly (no OCR yet)
        import pymupdf
        with pymupdf.open(stream=content, filetype="pdf") as doc:
            page_count = len(doc)

        # Create session immediately with placeholder data
        session = await session_service.create(
            pii_mapping={},
            anonymized_text="",
            page_texts=[],
            htoc_tree=None,
            htoc_status="processing",  # OCR in progress
            document_metadata={
                "filename": file.filename,
                "page_count": page_count,
                "size_bytes": len(content),
                "needs_ocr": True,
            }
        )

        # Launch OCR + PII + HTOC + BM25 all in background
        asyncio.create_task(
            _process_document_background(
                session.session_id, content, file.content_type,
                doc_type, ocr_language, pii_service, gemini,
                htoc_builder, session_service,
            )
        )

        return UploadResponse(
            session_id=session.session_id,
            filename=file.filename,
            page_count=page_count,
            detected_pii_count=0,
            needs_ocr=True,
            expires_in_seconds=settings.SESSION_TTL_SECONDS,
            htoc_status="processing",
        )

    # ── DIGITAL PATH: parse + PII are fast, only HTOC is backgrounded ──

    # 3. Extract text (fast — PyMuPDF, no API calls)
    try:
        raw_text = await parser.extract_async(content, file.content_type, doc_type, ocr_language)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse document: {str(e)}")

    # 4. Anonymize PII
    raw_page_texts = parser.page_texts
    joined_with_separators = PAGE_SEPARATOR.join(raw_page_texts)
    anonymized_joined, pii_mapping = await pii_service.anonymize(joined_with_separators)

    anonymized_pages = anonymized_joined.split(PAGE_SEPARATOR)
    anonymized_text = "\n\n".join(anonymized_pages)

    # 5. Create session immediately
    session = await session_service.create(
        pii_mapping=pii_mapping,
        anonymized_text=anonymized_text,
        page_texts=anonymized_pages,
        htoc_tree=None,
        htoc_status="building",
        document_metadata={
            "filename": file.filename,
            "page_count": parser.page_count,
            "size_bytes": len(content),
            "needs_ocr": False,
        }
    )

    # 6. Launch HTOC + BM25 build in background
    asyncio.create_task(
        _build_htoc_and_bm25(
            session.session_id, anonymized_pages, gemini, htoc_builder, session_service
        )
    )

    return UploadResponse(
        session_id=session.session_id,
        filename=file.filename,
        page_count=parser.page_count,
        detected_pii_count=len(pii_mapping),
        needs_ocr=False,
        expires_in_seconds=settings.SESSION_TTL_SECONDS,
        htoc_status="building",
    )


class HTOCNode(BaseModel):
    title: str
    node_id: str
    start_page: int
    end_page: int
    summary: str
    children: list = []


class HTOCTreeResponse(BaseModel):
    session_id: str
    filename: str
    total_nodes: int
    tree: Optional[dict] = None
    htoc_status: str


@router.get("/htoc-tree", response_model=HTOCTreeResponse)
async def get_htoc_tree(
    session_id: str = Header(..., alias="X-Session-ID"),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """View the HTOC tree for a document. Returns status if still building."""
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    status = session.htoc_status or ("ready" if session.htoc_tree else "pending")

    if not session.htoc_tree:
        return HTOCTreeResponse(
            session_id=session_id,
            filename=session.document_metadata.get("filename", "unknown"),
            total_nodes=0,
            tree=None,
            htoc_status=status,
        )

    return HTOCTreeResponse(
        session_id=session_id,
        filename=session.document_metadata.get("filename", "unknown"),
        total_nodes=_count_nodes(session.htoc_tree),
        tree=session.htoc_tree,
        htoc_status=status,
    )


@router.get("/htoc-status")
async def get_htoc_status(
    session_id: str = Header(..., alias="X-Session-ID"),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """Quick poll endpoint for frontend to check if processing is ready."""
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")
    return {
        "status": session.htoc_status or "pending",
        "has_htoc": session.htoc_tree is not None,
        "has_bm25": session.bm25_data is not None,
        "has_text": bool(session.anonymized_text),
    }


def _count_nodes(node: dict) -> int:
    """Count total nodes in the HTOC tree."""
    count = 1
    for child in node.get("children", []):
        count += _count_nodes(child)
    return count
