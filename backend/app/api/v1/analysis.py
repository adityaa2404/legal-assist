from fastapi import APIRouter, Depends, Header, HTTPException, Query
from app.services.session_service import SessionService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.gemini_client import GeminiClient
from app.services.pinecone_service import PineconeService
from app.core.dependencies import get_session_service, get_pii_service, get_gemini_client, get_pinecone_service
import logging
from app.models.analysis import AnalysisResponse

router = APIRouter()

@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_document(
    session_id: str = Header(..., alias="X-Session-ID"),
    analysis_type: str = Query(default='full'),
    session_service: SessionService = Depends(get_session_service),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    gemini: GeminiClient = Depends(get_gemini_client),
    pinecone_service: PineconeService = Depends(get_pinecone_service),
):
    # Note: The user spec said session_id: str = Header(...) which maps to 'session-id' header by default in FastAPI 
    # but let's stick to what's common or clarify. The spec example usage didn't show the header name explicitly 
    # other than `session_id: str = Header(...)`. 
    # If I use `Header(...)` the header name is `session-id`.
    
    # 1. Retrieve session (has PII mapping + extracted text)
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    # 2. Text is already anonymized from upload step
    anonymized_text = session.anonymized_text
    if not anonymized_text:
        raise HTTPException(400, "No document text found in session")

    # 3. Send to Gemini
    try:
        raw_result = await gemini.analyze_document(
            anonymized_text, analysis_type
        )
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

    # 4. De-anonymize the response
    result = pii_service.deanonymize_dict(
        raw_result, session.pii_mapping
    )

    # 5. Normalize AI output (Safety Layer)
    if isinstance(result.get("obligations"), str):
        result["obligations"] = [{"description": result["obligations"]}]
    elif not isinstance(result.get("obligations"), list):
        result["obligations"] = []

    if isinstance(result.get("missing_clauses"), str):
        result["missing_clauses"] = [result["missing_clauses"]]
    elif not isinstance(result.get("missing_clauses"), list):
        result["missing_clauses"] = []

    if not isinstance(result.get("parties"), list):
        result["parties"] = []
    else:
        for i, party in enumerate(result["parties"]):
            if isinstance(party, str):
                result["parties"][i] = {"role": "Party", "name": party}

    # 6. Enrich clauses with rulebook references from Pinecone
    try:
        clause_texts = [c["clause_text"] for c in result.get("key_clauses", [])]
        references = await pinecone_service.get_references(clause_texts)
        for clause, refs in zip(result["key_clauses"], references):
            clause["rulebook_references"] = refs
    except Exception as e:
        logging.warning(f"Pinecone enrichment failed (non-fatal): {e}")

    return AnalysisResponse(**result)
