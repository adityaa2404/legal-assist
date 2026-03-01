from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.document_parser import DocumentParser
from app.services.session_service import SessionService
from app.core.dependencies import get_pii_service, get_parser, get_session_service
from app.core.config import settings
from pydantic import BaseModel

router = APIRouter()

class UploadResponse(BaseModel):
    session_id: str
    filename: str
    page_count: int
    detected_pii_count: int
    expires_in_seconds: int

ALLOWED_TYPES = [
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword"
]

@router.post("/upload", response_model=UploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    parser: DocumentParser = Depends(get_parser),
    session_service: SessionService = Depends(get_session_service),
):
    # 1. Validate file type
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(400, "Only PDF and DOCX supported")

    # 2. Read file into memory (never touches disk)
    content = await file.read()
    if len(content) > settings.MAX_FILE_SIZE_MB * 1024 * 1024:
        raise HTTPException(413, "File too large")

    # 3. Extract text in memory
    try:
        raw_text = parser.extract(content, file.content_type)
    except Exception as e:
        raise HTTPException(500, f"Failed to parse document: {str(e)}")

    # 4. Anonymize PII
    anonymized_text, pii_mapping = await pii_service.anonymize(raw_text)

    # 5. Create session with mapping (no document stored)
    session = await session_service.create(
        pii_mapping=pii_mapping,
        anonymized_text=anonymized_text,
        document_metadata={
            "filename": file.filename,
            "page_count": parser.page_count,
            "size_bytes": len(content)
        }
    )

    # 6. content and raw_text go out of scope = garbage collected
    return UploadResponse(
        session_id=session.session_id,
        filename=file.filename,
        page_count=parser.page_count,
        detected_pii_count=len(pii_mapping),
        expires_in_seconds=settings.SESSION_TTL_SECONDS
    )
