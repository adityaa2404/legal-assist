from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response
from app.services.session_service import SessionService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.gemini_client import GeminiClient
from app.services.tree_search import TreeSearchService
from app.core.dependencies import (
    get_session_service, get_pii_service, get_gemini_client,
    get_current_user, get_tree_search,
)
import logging
from app.models.analysis import AnalysisResponse
from app.services.report_generator import create_pdf_from_analysis

logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_result(result: dict) -> dict:
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

    return result


async def _get_or_run_analysis(
    session_id: str,
    analysis_type: str,
    session_service: SessionService,
    pii_service: PIIAnonymizer,
    gemini: GeminiClient,
    tree_search: TreeSearchService = None,
) -> dict:
    """Return cached analysis if available, otherwise run Gemini and cache."""
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    anonymized_text = session.anonymized_text
    if not anonymized_text:
        raise HTTPException(400, "No document text found in session")

    # Check cache first
    cached = await session_service.get_analysis(session_id, analysis_type)
    if cached:
        return cached

    # Build structured context from HTOC if available
    document_context = anonymized_text
    has_htoc = session.htoc_tree and session.page_texts

    if has_htoc and tree_search:
        try:
            # Use tree-structured context: sections are organized hierarchically
            # with headers and page references for better analysis
            structured_context = await tree_search.search_for_analysis(
                tree=session.htoc_tree,
                page_texts=session.page_texts,
                gemini_client=gemini,
            )
            document_context = structured_context
            logger.info("Using HTOC-structured context for analysis")
        except Exception as e:
            logger.warning(f"HTOC analysis context failed, using full text: {e}")

    # Run Gemini
    try:
        raw_result = await gemini.analyze_document(document_context, analysis_type)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

    result = pii_service.deanonymize_dict(raw_result, session.pii_mapping)
    result = _normalize_result(result)

    # Cache for future use (report endpoint)
    await session_service.save_analysis(session_id, analysis_type, result)

    return result


@router.post("/analyze", response_model=AnalysisResponse)
async def analyze_document(
    session_id: str = Header(..., alias="X-Session-ID"),
    analysis_type: str = Query(default='full'),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    gemini: GeminiClient = Depends(get_gemini_client),
    tree_search: TreeSearchService = Depends(get_tree_search),
):
    result = await _get_or_run_analysis(
        session_id, analysis_type, session_service, pii_service, gemini, tree_search
    )
    return AnalysisResponse(**result)


@router.get("/analyze/report")
async def get_analysis_report(
    session_id: str = Header(..., alias="X-Session-ID"),
    analysis_type: str = Query(default='full'),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    gemini: GeminiClient = Depends(get_gemini_client),
    tree_search: TreeSearchService = Depends(get_tree_search),
):
    result = await _get_or_run_analysis(
        session_id, analysis_type, session_service, pii_service, gemini, tree_search
    )

    filename = "Legal Analysis Report"
    try:
        pdf_bytes = create_pdf_from_analysis(result, filename, analysis_type)
    except Exception as e:
        logging.error(f"PDF generation failed: {e}")
        raise HTTPException(500, f"PDF report generation failed: {str(e)}")

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{session_id}.pdf"}
    )
