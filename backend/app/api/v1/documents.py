from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Header, Query
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.document_parser import DocumentParser
from app.services.session_service import SessionService
from app.services.gemini_client import GeminiClient
from app.services.htoc_builder import HTOCBuilder
from app.core.dependencies import (
    get_pii_service, get_parser, get_session_service,
    get_current_user, get_gemini_client, get_htoc_builder,
)
from app.core.config import settings
from pydantic import BaseModel
from typing import Optional, Literal
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
    htoc_sections: Optional[int] = None  # Number of HTOC sections identified

ALLOWED_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword"
]

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

    # 3. Extract text
    #    digital  → PyMuPDF (fast, any language)
    #    scanned  → Sarvam AI (22 Indian languages + English)
    try:
        raw_text = await parser.extract_async(content, file.content_type, doc_type, ocr_language)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse document: {str(e)}")

    # 4. Anonymize PII — join pages with separator, anonymize together, split back
    raw_page_texts = parser.page_texts
    joined_with_separators = PAGE_SEPARATOR.join(raw_page_texts)
    anonymized_joined, pii_mapping = await pii_service.anonymize(joined_with_separators)

    # Split back into per-page anonymized text
    anonymized_pages = anonymized_joined.split(PAGE_SEPARATOR)
    # Also create the full anonymized text (without separators)
    anonymized_text = "\n\n".join(anonymized_pages)

    # 5. Build HTOC tree from anonymized pages using Gemini
    htoc_tree = None
    htoc_section_count = None
    try:
        htoc_tree = await htoc_builder.build_tree(anonymized_pages, gemini)
        htoc_section_count = _count_nodes(htoc_tree)
        logger.info(f"HTOC tree built with {htoc_section_count} sections for {file.filename}")
    except Exception as e:
        logger.warning(f"HTOC building failed, will use full-text fallback: {e}")

    # 6. Create session with mapping, pages, and HTOC tree
    session = await session_service.create(
        pii_mapping=pii_mapping,
        anonymized_text=anonymized_text,
        page_texts=anonymized_pages,
        htoc_tree=htoc_tree,
        document_metadata={
            "filename": file.filename,
            "page_count": parser.page_count,
            "size_bytes": len(content),
            "needs_ocr": parser.needs_ocr,
        }
    )

    # 7. content and raw_text go out of scope = garbage collected
    return UploadResponse(
        session_id=session.session_id,
        filename=file.filename,
        page_count=parser.page_count,
        detected_pii_count=len(pii_mapping),
        needs_ocr=parser.needs_ocr,
        expires_in_seconds=settings.SESSION_TTL_SECONDS,
        htoc_sections=htoc_section_count,
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


@router.get("/htoc-tree", response_model=HTOCTreeResponse)
async def get_htoc_tree(
    session_id: str = Header(..., alias="X-Session-ID"),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """View the HTOC (Hierarchical Table of Contents) tree for a document."""
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    if not session.htoc_tree:
        raise HTTPException(404, "No HTOC tree found for this session. Tree building may have failed during upload.")

    return HTOCTreeResponse(
        session_id=session_id,
        filename=session.document_metadata.get("filename", "unknown"),
        total_nodes=_count_nodes(session.htoc_tree),
        tree=session.htoc_tree,
    )


def _count_nodes(node: dict) -> int:
    """Count total nodes in the HTOC tree."""
    count = 1
    for child in node.get("children", []):
        count += _count_nodes(child)
    return count
