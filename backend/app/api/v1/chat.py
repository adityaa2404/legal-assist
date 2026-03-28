import json
import logging
import re
from fastapi import APIRouter, Depends, Header, HTTPException, Body
from fastapi.responses import StreamingResponse
from app.services.session_service import SessionService
from app.services.pii_anonymizer import PIIAnonymizer
from app.services.gemini_client import GeminiClient
from app.services.tree_search import TreeSearchService
from app.services.bm25_search import BM25SearchService, compute_query_hash
from app.core.dependencies import (
    get_session_service, get_pii_service, get_gemini_client,
    get_current_user, get_tree_search,
)
from app.models.chat import ChatRequest, ChatResponse

# Regex to detect incomplete PII tokens at the end of a chunk (e.g. "[PERS" or "[PERSON_1")
_PARTIAL_TOKEN_RE = re.compile(r'\[[A-Z_0-9]*$')

logger = logging.getLogger(__name__)

router = APIRouter()

# Max history messages to send to LLM (saves tokens on long conversations)
MAX_HISTORY_MESSAGES = 8  # last 4 exchanges (user+assistant pairs)
# If history is longer, summarize old messages into a single context line
SUMMARIZE_AFTER = 8


def _trim_history(history: list) -> list:
    """
    Trim chat history for long conversations to save tokens.
    Keeps last MAX_HISTORY_MESSAGES, summarizes older ones into 1 context line.
    """
    if len(history) <= MAX_HISTORY_MESSAGES:
        return history

    old = history[:-MAX_HISTORY_MESSAGES]
    recent = history[-MAX_HISTORY_MESSAGES:]

    # Summarize old messages into a brief context line
    topics = []
    for msg in old:
        if msg["role"] == "user":
            # Take first 80 chars of each old user question
            topics.append(msg["content"][:80].strip())

    summary = "Earlier in this conversation, we discussed: " + "; ".join(topics[-5:])
    return [{"role": "user", "content": summary}, {"role": "assistant", "content": "Understood, I have that context."}] + recent


def _build_search_query(question: str, history: list) -> str:
    """Build a context-aware query for retrieval (so follow-ups work)."""
    if not history:
        return question

    recent = history[-4:]  # last 2 exchanges
    context_lines = []
    for msg in recent:
        prefix = "User" if msg["role"] == "user" else "Assistant"
        context_lines.append(f"{prefix}: {msg['content'][:150]}")
    return (
        "Conversation context:\n"
        + "\n".join(context_lines)
        + f"\n\nCurrent question: {question}"
    )


def _get_bm25_service(session) -> BM25SearchService:
    """Load BM25 index from session data."""
    bm25 = BM25SearchService()
    if session.bm25_data:
        bm25.load_from_data(session.bm25_data)
    elif session.page_texts:
        # Fallback: build index on-the-fly if bm25_data not stored yet (HTOC still building)
        bm25.build_index(session.page_texts, session.htoc_tree)
    return bm25


# ──────────────────────────────────────────────────────────────────────
#  NON-STREAMING CHAT (original endpoint, kept for compatibility)
# ──────────────────────────────────────────────────────────────────────

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
    # 1. Retrieve session (with ownership check)
    session = await session_service.get_for_user(session_id, current_user)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    # Check if document is still being processed (scanned OCR in progress)
    status = getattr(session, 'htoc_status', None) or 'pending'
    if not session.anonymized_text and status in ("processing",):
        raise HTTPException(202, "Document is still being processed (OCR in progress). Please wait a few seconds.")

    # 2. Anonymize the question (history is already short user text — anonymize only the new message)
    anonymized_question, _ = await pii_service.anonymize(request.message)

    anonymized_history = []
    for msg in request.history:
        anonymized_content, _ = await pii_service.anonymize(msg.content)
        anonymized_history.append({"role": msg.role, "content": anonymized_content})

    # 3. Check response cache (exact same question = instant response)
    query_hash = compute_query_hash(session_id, anonymized_question)
    cached = await session_service.get_cached_chat(session_id, query_hash)
    if cached:
        final_response = pii_service.deanonymize(cached["response"], session.pii_mapping)
        return ChatResponse(
            response=final_response,
            source_sections=cached.get("source_sections"),
        )

    # 4. Trim history for long conversations (saves tokens)
    trimmed_history = _trim_history(anonymized_history)

    # 5. RETRIEVAL — BM25 hybrid (fast, free) with LLM fallback
    source_sections = []
    search_query = _build_search_query(anonymized_question, anonymized_history)
    use_fulltext = False

    # Try BM25 first (free, <5ms)
    bm25 = _get_bm25_service(session)
    has_bm25 = bm25._index is not None

    if has_bm25 and session.page_texts:
        search_result = bm25.search(search_query, session.page_texts)
        confidence = search_result.get("confidence", "low")

        if confidence == "low" and session.htoc_tree:
            # BM25 failed (semantic query) — fall back to LLM tree search
            logger.info("BM25 low confidence, falling back to LLM tree search")
            try:
                search_result = await tree_search.search(
                    tree=session.htoc_tree,
                    query=search_query,
                    page_texts=session.page_texts,
                    gemini_client=gemini,
                )
            except Exception as e:
                logger.warning("LLM tree search also failed: %s", e)
                # search_result from BM25 is still usable

        context = search_result["context"]
        source_sections = search_result.get("source_sections", [])
        source_info = ", ".join(
            "{} (p.{})".format(s["title"], s["pages"]) for s in source_sections
        )
        logger.info("Retrieved %d sections: %s", len(source_sections), source_info)

        anonymized_response = await gemini.chat_with_context(
            question=anonymized_question,
            context=context,
            chat_history=trimmed_history,
            source_info=source_info,
        )
    else:
        # No index yet (HTOC still building) — use full-text fallback
        use_fulltext = True

    if use_fulltext:
        try:
            anonymized_response = await gemini.chat(
                anonymized_question,
                session.anonymized_text,
                trimmed_history,
            )
        except Exception as e:
            logger.error("Chat failed: %s", e)
            raise HTTPException(500, "Chat failed. Please try again.")

    # 6. De-anonymize response
    final_response = pii_service.deanonymize(anonymized_response, session.pii_mapping)

    # 7. Cache the response for repeated questions (async, non-blocking)
    try:
        await session_service.cache_chat_response(
            session_id, query_hash, anonymized_response,
            source_sections if source_sections else []
        )
    except Exception:
        pass  # Cache failure is non-critical

    return ChatResponse(
        response=final_response,
        source_sections=source_sections if source_sections else None,
    )


# ──────────────────────────────────────────────────────────────────────
#  STREAMING CHAT (SSE — tokens arrive as they're generated)
# ──────────────────────────────────────────────────────────────────────

@router.post("/chat/stream")
async def chat_with_document_stream(
    request: ChatRequest,
    session_id: str = Header(..., alias="X-Session-ID"),
    current_user: str = Depends(get_current_user),
    session_service: SessionService = Depends(get_session_service),
    pii_service: PIIAnonymizer = Depends(get_pii_service),
    gemini: GeminiClient = Depends(get_gemini_client),
    tree_search: TreeSearchService = Depends(get_tree_search),
):
    """
    Streaming chat endpoint. Returns Server-Sent Events (SSE):
      - event: token   → data: {"text": "chunk of response"}
      - event: sources → data: {"source_sections": [...]}
      - event: done    → data: {}
      - event: error   → data: {"error": "message"}
    """
    # 1. Retrieve session (with ownership check)
    session = await session_service.get_for_user(session_id, current_user)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    # Check if document is still being processed
    status = getattr(session, 'htoc_status', None) or 'pending'
    if not session.anonymized_text and status in ("processing",):
        raise HTTPException(202, "Document is still being processed (OCR in progress). Please wait a few seconds.")

    # 2. Anonymize
    anonymized_question, _ = await pii_service.anonymize(request.message)
    anonymized_history = []
    for msg in request.history:
        anonymized_content, _ = await pii_service.anonymize(msg.content)
        anonymized_history.append({"role": msg.role, "content": anonymized_content})

    # 3. Check cache
    query_hash = compute_query_hash(session_id, anonymized_question)
    cached = await session_service.get_cached_chat(session_id, query_hash)

    if cached:
        # Return cached response as a single stream event
        async def cached_stream():
            final = pii_service.deanonymize(cached["response"], session.pii_mapping)
            yield f"event: token\ndata: {json.dumps({'text': final})}\n\n"
            if cached.get("source_sections"):
                yield f"event: sources\ndata: {json.dumps({'source_sections': cached['source_sections']})}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # 4. Trim history
    trimmed_history = _trim_history(anonymized_history)

    # 5. Retrieve context
    search_query = _build_search_query(anonymized_question, anonymized_history)
    source_sections = []
    context = None
    source_info = ""

    bm25 = _get_bm25_service(session)
    has_bm25 = bm25._index is not None

    if has_bm25 and session.page_texts:
        search_result = bm25.search(search_query, session.page_texts)
        confidence = search_result.get("confidence", "low")

        if confidence == "low" and session.htoc_tree:
            try:
                search_result = await tree_search.search(
                    tree=session.htoc_tree, query=search_query,
                    page_texts=session.page_texts, gemini_client=gemini,
                )
            except Exception:
                pass

        context = search_result["context"]
        source_sections = search_result.get("source_sections", [])
        source_info = ", ".join(
            "{} (p.{})".format(s["title"], s["pages"]) for s in source_sections
        )

    # 6. Stream response with buffered deanonymization
    #    Tokens like [PERSON_1] can be split across chunks, so we buffer
    #    any trailing partial "[..." and flush it with the next chunk.
    async def event_stream():
        full_response_parts = []
        buffer = ""

        try:
            # Send sources first so frontend can display them immediately
            if source_sections:
                yield f"event: sources\ndata: {json.dumps({'source_sections': source_sections})}\n\n"

            # Stream LLM response
            if context:
                stream = gemini.chat_with_context_stream(
                    question=anonymized_question,
                    context=context,
                    chat_history=trimmed_history,
                    source_info=source_info,
                )
            else:
                stream = gemini.chat_stream(
                    anonymized_question,
                    session.anonymized_text,
                    trimmed_history,
                )

            async for chunk in stream:
                full_response_parts.append(chunk)  # Store anonymized for cache
                buffer += chunk

                # Check for incomplete PII token at end of buffer
                partial = _PARTIAL_TOKEN_RE.search(buffer)
                if partial:
                    # Hold back the partial token, emit everything before it
                    emit = buffer[:partial.start()]
                    buffer = buffer[partial.start():]
                else:
                    emit = buffer
                    buffer = ""

                if emit:
                    clean_chunk = pii_service.deanonymize(emit, session.pii_mapping)
                    yield f"event: token\ndata: {json.dumps({'text': clean_chunk})}\n\n"

            # Flush remaining buffer
            if buffer:
                clean_chunk = pii_service.deanonymize(buffer, session.pii_mapping)
                yield f"event: token\ndata: {json.dumps({'text': clean_chunk})}\n\n"

            yield "event: done\ndata: {}\n\n"

            # Cache the full response (async)
            full_anonymized = "".join(full_response_parts)
            try:
                await session_service.cache_chat_response(
                    session_id, query_hash, full_anonymized,
                    source_sections if source_sections else []
                )
            except Exception:
                pass

        except Exception as e:
            logger.error("Stream error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': 'An error occurred during streaming. Please try again.'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
