from fastapi import APIRouter, Depends, Header, HTTPException, Body
from app.services.session_service import SessionService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.gemini_client import GeminiClient
from app.services.tree_search import TreeSearchService
from app.core.dependencies import (
    get_session_service, get_pii_service, get_gemini_client,
    get_current_user, get_tree_search,
)
from app.models.chat import ChatRequest, ChatResponse
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

@router.post("/chat", response_model=ChatResponse)
async def chat_with_document(
    request: ChatRequest,
    session_id: str = Header(..., alias="X-Session-ID"),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    gemini: GeminiClient = Depends(get_gemini_client),
    tree_search: TreeSearchService = Depends(get_tree_search),
):
    # 1. Retrieve session
    session = await session_service.get(session_id)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    # 2. Anonymize the question and history
    anonymized_question, _ = await pii_service.anonymize(request.message)

    anonymized_history = []
    for msg in request.history:
        anonymized_content, _ = await pii_service.anonymize(msg.content)
        anonymized_history.append({"role": msg.role, "content": anonymized_content})

    # 3. HTOC Tree Search (Vectorless RAG) or Full-Text Fallback
    source_sections = []
    has_htoc = session.htoc_tree and session.page_texts

    if has_htoc:
        # === VECTORLESS RAG PATH ===
        # LLM reasons over the HTOC tree to find relevant sections
        try:
            search_result = await tree_search.search(
                tree=session.htoc_tree,
                query=anonymized_question,
                page_texts=session.page_texts,
                gemini_client=gemini,
            )
            context = search_result["context"]
            source_sections = search_result.get("source_sections", [])
            source_info = ", ".join(
                "{} (p.{})".format(s["title"], s["pages"]) for s in source_sections
            )
            logger.info(
                "Tree search selected %d sections: %s",
                len(source_sections),
                source_info,
            )

            # Use targeted context chat
            anonymized_response = await gemini.chat_with_context(
                question=anonymized_question,
                context=context,
                chat_history=anonymized_history,
                source_info=source_info,
            )
        except Exception as e:
            logger.warning("Tree search failed, falling back to full text: %s", e)
            has_htoc = False  # Fall through to full-text path

    if not has_htoc:
        # === FULL-TEXT FALLBACK (original behavior) ===
        try:
            anonymized_response = await gemini.chat(
                anonymized_question,
                session.anonymized_text,
                anonymized_history,
            )
        except Exception as e:
            raise HTTPException(500, "Chat failed: {}".format(str(e)))

    # 4. De-anonymize response
    final_response = pii_service.deanonymize(anonymized_response, session.pii_mapping)

    return ChatResponse(
        response=final_response,
        source_sections=source_sections if source_sections else None,
    )
