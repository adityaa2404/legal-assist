from fastapi import APIRouter, Depends, Query, HTTPException, Body
from app.services.history_service import HistoryService
from app.services.session_service import SessionService
from app.services.bm25_search import BM25SearchService
from app.core.dependencies import get_current_user, get_session_service
import logging

logger = logging.getLogger(__name__)

router = APIRouter()


def get_history_service() -> HistoryService:
    return HistoryService()


@router.get("/history")
async def get_analysis_history(
    limit: int = Query(default=20, le=50),
    skip: int = Query(default=0, ge=0),
    current_user: str = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
):
    """Get user's past analysis results (lightweight, no chat data)."""
    items = await history_service.get_user_history(current_user, limit=limit, skip=skip)
    return {"history": items, "count": len(items)}


@router.delete("/history")
async def delete_history_item(
    created_at: str = Body(..., embed=True),
    current_user: str = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
):
    """Delete a single analysis from history."""
    deleted = await history_service.delete_history_item(current_user, created_at)
    if not deleted:
        raise HTTPException(404, "History item not found")
    return {"message": "Analysis deleted"}


@router.post("/history/restore")
async def restore_session_from_history(
    created_at: str = Body(..., embed=True),
    current_user: str = Depends(get_current_user),
    history_service: HistoryService = Depends(get_history_service),
    session_service: SessionService = Depends(get_session_service),
):
    """Restore a history item into a live session so the user can chat with it."""
    item = await history_service.get_full_history_item(current_user, created_at)
    if not item:
        raise HTTPException(404, "History item not found")

    page_texts = item.get("page_texts", [])
    if not page_texts:
        raise HTTPException(400, "This history item has no document data for chat")

    htoc_tree = item.get("htoc_tree")
    pii_mapping = item.get("pii_mapping", {})

    # Rebuild BM25 index from stored page_texts
    bm25 = BM25SearchService()
    bm25.build_index(page_texts, htoc_tree)
    bm25_data = bm25.get_serializable_data()

    # Create a new session with the restored data
    session = await session_service.create(
        pii_mapping=pii_mapping,
        anonymized_text="\n\n".join(page_texts),
        page_texts=page_texts,
        htoc_tree=htoc_tree,
        bm25_data=bm25_data,
        htoc_status="ready",
        document_metadata={
            "filename": item.get("filename", "Restored Document"),
            "page_count": item.get("page_count", len(page_texts)),
            "size_bytes": 0,
        },
    )

    # Cache the analysis too so they don't need to re-run it
    analysis_data = {
        "summary": item.get("summary", ""),
        "document_type": item.get("document_type", ""),
        "overall_risk_score": item.get("overall_risk_score", 0),
        "parties": item.get("parties", []),
        "key_clauses": item.get("key_clauses", []),
        "risks": item.get("risks", []),
        "obligations": item.get("obligations", []),
        "missing_clauses": item.get("missing_clauses", []),
    }
    await session_service.save_analysis(session.session_id, "full", analysis_data)

    return {
        "session_id": session.session_id,
        "filename": item.get("filename"),
        "page_count": item.get("page_count"),
        "message": "Session restored — you can now chat with this document",
    }
