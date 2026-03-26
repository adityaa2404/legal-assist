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
from app.services.history_service import HistoryService

logger = logging.getLogger(__name__)

router = APIRouter()


def _derive_short_from_full(full: dict) -> dict:
    """
    Derive a short analysis from a full one — saves 1 Gemini call.
    Trims summaries, limits clauses/risks, keeps structure identical.
    """
    import copy
    short = copy.deepcopy(full)

    # Trim summary to first 2 sentences
    summary = short.get("summary", "")
    sentences = summary.replace("\n", " ").split(". ")
    if len(sentences) > 2:
        short["summary"] = ". ".join(sentences[:2]) + "."

    # Limit key clauses to top 5 (critical + important first)
    clauses = short.get("key_clauses", [])
    importance_order = {"critical": 0, "important": 1, "standard": 2}
    clauses.sort(key=lambda c: importance_order.get(c.get("importance", "standard"), 2))
    short["key_clauses"] = clauses[:5]
    for clause in short["key_clauses"]:
        # Trim clause_text to 150 chars
        text = clause.get("clause_text", "")
        if len(text) > 150:
            clause["clause_text"] = text[:150].rsplit(" ", 1)[0] + "..."
        # Trim plain_english to 1 sentence
        pe = clause.get("plain_english", "")
        pe_sentences = pe.split(". ")
        if len(pe_sentences) > 1:
            clause["plain_english"] = pe_sentences[0] + "."

    # Limit risks to top 5 (high severity first)
    risks = short.get("risks", [])
    severity_order = {"high": 0, "medium": 1, "low": 2}
    risks.sort(key=lambda r: severity_order.get(r.get("severity", "low"), 2))
    short["risks"] = risks[:5]
    for risk in short["risks"]:
        desc = risk.get("description", "")
        desc_sentences = desc.split(". ")
        if len(desc_sentences) > 1:
            risk["description"] = desc_sentences[0] + "."
        rec = risk.get("recommendation", "")
        rec_sentences = rec.split(". ")
        if len(rec_sentences) > 1:
            risk["recommendation"] = rec_sentences[0] + "."

    # Limit obligations to 5
    short["obligations"] = short.get("obligations", [])[:5]

    # Keep missing_clauses, overall_risk_score, parties, document_type as-is

    return short


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
        status = getattr(session, 'htoc_status', None) or 'pending'
        if status in ("processing", "building"):
            raise HTTPException(202, "Document is still being processed. Please wait and try again in a few seconds.")
        raise HTTPException(400, "No document text found in session")

    # For short analysis, try to derive from cached full analysis first (saves 1 Gemini call)
    if analysis_type == "short":
        cached_full = await session_service.get_analysis(session_id, "full")
        if cached_full:
            short_result = _derive_short_from_full(cached_full)
            await session_service.save_analysis(session_id, "short", short_result)
            return short_result

    # Check cache for this specific analysis type
    cached = await session_service.get_analysis(session_id, analysis_type)
    if cached:
        return cached

    # Build structured context from HTOC if available
    document_context = anonymized_text
    has_htoc = session.htoc_tree and session.page_texts

    if has_htoc and tree_search:
        try:
            structured_context = await tree_search.search_for_analysis(
                tree=session.htoc_tree,
                page_texts=session.page_texts,
                gemini_client=gemini,
            )
            document_context = structured_context
            logger.info("Using HTOC-structured context for analysis")
        except Exception as e:
            logger.warning(f"HTOC analysis context failed, using full text: {e}")

    # Always run full analysis — short can be derived from it
    run_type = "full" if analysis_type == "short" else analysis_type

    try:
        raw_result = await gemini.analyze_document(document_context, run_type)
    except Exception as e:
        raise HTTPException(500, f"Analysis failed: {str(e)}")

    result = pii_service.deanonymize_dict(raw_result, session.pii_mapping)
    result = _normalize_result(result)

    # Cache the full analysis
    await session_service.save_analysis(session_id, run_type, result)

    # If short was requested, derive it from the full we just ran
    if analysis_type == "short":
        short_result = _derive_short_from_full(result)
        await session_service.save_analysis(session_id, "short", short_result)
        return short_result

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

    # Save to user's history (only full analysis, skip if already cached = already saved)
    if analysis_type == "full":
        cached_before = await session_service.get_analysis(session_id, "_history_saved")
        if not cached_before:
            try:
                session = await session_service.get(session_id)
                history = HistoryService()
                await history.save(
                    current_user, result, session.document_metadata,
                    page_texts=session.page_texts,
                    htoc_tree=session.htoc_tree,
                    pii_mapping=session.pii_mapping,
                )
                await session_service.save_analysis(session_id, "_history_saved", {"saved": True})
            except Exception as e:
                logger.warning(f"Failed to save history: {e}")

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
