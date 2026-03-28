from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from app.services.session_service import SessionService
from app.core.dependencies import get_session_service, get_current_user
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


class CompareRequest(BaseModel):
    session_id_a: str
    session_id_b: str


class ClauseDiff(BaseModel):
    clause_title: str
    status: str  # "only_a", "only_b", "both", "different"
    doc_a: Optional[str] = None
    doc_b: Optional[str] = None
    plain_a: Optional[str] = None
    plain_b: Optional[str] = None


class RiskDiff(BaseModel):
    risk_title: str
    status: str  # "only_a", "only_b", "both"
    severity_a: Optional[str] = None
    severity_b: Optional[str] = None
    description_a: Optional[str] = None
    description_b: Optional[str] = None


class CompareResponse(BaseModel):
    doc_a_name: str
    doc_b_name: str
    score_a: int
    score_b: int
    summary_a: str
    summary_b: str
    clause_diffs: List[ClauseDiff]
    risk_diffs: List[RiskDiff]
    missing_only_a: List[str]
    missing_only_b: List[str]
    missing_both: List[str]


def _compare_clauses(clauses_a: list, clauses_b: list) -> List[dict]:
    """Compare clauses from two documents by title similarity."""
    diffs = []
    titles_b = {c.get("clause_title", "").lower(): c for c in clauses_b}
    matched_b = set()

    for ca in clauses_a:
        title_a = ca.get("clause_title", "")
        title_lower = title_a.lower()
        if title_lower in titles_b:
            cb = titles_b[title_lower]
            matched_b.add(title_lower)
            text_same = ca.get("clause_text", "").strip() == cb.get("clause_text", "").strip()
            diffs.append({
                "clause_title": title_a,
                "status": "both" if text_same else "different",
                "doc_a": ca.get("clause_text", ""),
                "doc_b": cb.get("clause_text", ""),
                "plain_a": ca.get("plain_english", ""),
                "plain_b": cb.get("plain_english", ""),
            })
        else:
            diffs.append({
                "clause_title": title_a,
                "status": "only_a",
                "doc_a": ca.get("clause_text", ""),
                "plain_a": ca.get("plain_english", ""),
            })

    for cb in clauses_b:
        title_lower = cb.get("clause_title", "").lower()
        if title_lower not in matched_b:
            diffs.append({
                "clause_title": cb.get("clause_title", ""),
                "status": "only_b",
                "doc_b": cb.get("clause_text", ""),
                "plain_b": cb.get("plain_english", ""),
            })

    return diffs


def _compare_risks(risks_a: list, risks_b: list) -> List[dict]:
    """Compare risks from two documents."""
    diffs = []
    titles_b = {r.get("risk_title", "").lower(): r for r in risks_b}
    matched_b = set()

    for ra in risks_a:
        title_a = ra.get("risk_title", "")
        title_lower = title_a.lower()
        if title_lower in titles_b:
            rb = titles_b[title_lower]
            matched_b.add(title_lower)
            diffs.append({
                "risk_title": title_a,
                "status": "both",
                "severity_a": ra.get("severity"),
                "severity_b": rb.get("severity"),
                "description_a": ra.get("description"),
                "description_b": rb.get("description"),
            })
        else:
            diffs.append({
                "risk_title": title_a,
                "status": "only_a",
                "severity_a": ra.get("severity"),
                "description_a": ra.get("description"),
            })

    for rb in risks_b:
        title_lower = rb.get("risk_title", "").lower()
        if title_lower not in matched_b:
            diffs.append({
                "risk_title": rb.get("risk_title", ""),
                "status": "only_b",
                "severity_b": rb.get("severity"),
                "description_b": rb.get("description"),
            })

    return diffs


@router.post("/compare", response_model=CompareResponse)
async def compare_documents(
    body: CompareRequest,
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
):
    """Compare analyses from two documents."""
    # Verify session ownership
    session_a = await session_service.get_for_user(body.session_id_a, current_user)
    session_b = await session_service.get_for_user(body.session_id_b, current_user)
    if not session_a:
        raise HTTPException(404, "Session A expired or not found")
    if not session_b:
        raise HTTPException(404, "Session B expired or not found")

    # Load cached analyses
    analysis_a = await session_service.get_analysis(body.session_id_a, "full")
    analysis_b = await session_service.get_analysis(body.session_id_b, "full")

    if not analysis_a:
        raise HTTPException(404, "No analysis found for document A. Run analysis first.")
    if not analysis_b:
        raise HTTPException(404, "No analysis found for document B. Run analysis first.")

    doc_a_name = session_a.document_metadata.get("filename", "Document A") if session_a else "Document A"
    doc_b_name = session_b.document_metadata.get("filename", "Document B") if session_b else "Document B"

    # Compare clauses
    clause_diffs = _compare_clauses(
        analysis_a.get("key_clauses", []),
        analysis_b.get("key_clauses", []),
    )

    # Compare risks
    risk_diffs = _compare_risks(
        analysis_a.get("risks", []),
        analysis_b.get("risks", []),
    )

    # Compare missing clauses
    missing_a = set(analysis_a.get("missing_clauses", []))
    missing_b = set(analysis_b.get("missing_clauses", []))

    return CompareResponse(
        doc_a_name=doc_a_name,
        doc_b_name=doc_b_name,
        score_a=analysis_a.get("overall_risk_score", 0),
        score_b=analysis_b.get("overall_risk_score", 0),
        summary_a=analysis_a.get("summary", ""),
        summary_b=analysis_b.get("summary", ""),
        clause_diffs=clause_diffs,
        risk_diffs=risk_diffs,
        missing_only_a=list(missing_a - missing_b),
        missing_only_b=list(missing_b - missing_a),
        missing_both=list(missing_a & missing_b),
    )
