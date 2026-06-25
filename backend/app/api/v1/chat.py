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

# P7: Token-aware history trim — budget in approximate tokens (chars / 4)
MAX_HISTORY_CHARS = 24000  # ~6000 tokens; leaves room for context + query + response


def _trim_history(history: list) -> list:
    """
    Trim chat history to fit within token budget.
    Walks backwards from most recent, keeps messages until budget is exhausted.
    Prepends a summary stub for dropped messages so the LLM has context.
    """
    kept = []
    budget = MAX_HISTORY_CHARS
    for msg in reversed(history):
        cost = len(msg["content"])
        if budget - cost < 0:
            break
        kept.append(msg)
        budget -= cost
    kept.reverse()

    if len(kept) < len(history):
        old = history[:len(history) - len(kept)]
        old_topics = [m["content"][:80].strip() for m in old if m["role"] == "user"]
        summary = "Earlier we discussed: " + "; ".join(old_topics[-5:])
        kept = [
            {"role": "user", "content": summary},
            {"role": "assistant", "content": "Understood, I have that context."},
        ] + kept

    return kept


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
        # Fallback: build index on-the-fly (HTOC still building)
        bm25.build_index(session.page_texts, session.htoc_tree, page_chunks=session.page_chunks)
    return bm25


async def _understand_query(query: str, gemini: GeminiClient, provider: str) -> dict:
    """
    Single Gemini call (temp=0) that returns everything retrieval needs:
    - intent: how much of the document to retrieve
    - expanded_query: original query + legal synonyms, used as BM25 token input
    - key_terms: priority tokens for HTOC section title matching

    Replaces both the old intent classification call AND the embedding call.
    One call, ~500ms, no vector dependency.
    """
    prompt = (
        "You are a legal document search expert. Analyze this query and return a JSON object.\n\n"
        f"Query: {query}\n\n"
        "Return ONLY valid JSON:\n"
        "{\n"
        '  "intent": "exhaustive" | "comparative" | "targeted",\n'
        '  "expanded_query": "<original query rephrased with legal synonyms added>",\n'
        '  "key_terms": ["<term1>", "<term2>", "<term3>"]\n'
        "}\n\n"
        "Rules:\n"
        "- intent=exhaustive: user wants ALL items (all clauses, all parties, list everything)\n"
        "- intent=comparative: user wants to compare two or more things\n"
        "- intent=targeted: user wants one specific piece of information\n"
        "- expanded_query: rewrite the query adding common legal synonyms so BM25 can match sections that use different words. "
        "Example: 'counterparty responsibilities' → 'counterparty responsibilities obligations duties liabilities'\n"
        "- key_terms: 2-4 most important search tokens from the query (single words, lowercase)\n"
        "- Return ONLY valid JSON, no explanation"
    )
    try:
        result = await gemini.generate_json(prompt, provider=provider)
        intent = result.get("intent", "targeted")
        if intent not in ("exhaustive", "comparative", "targeted"):
            intent = "targeted"
        expanded = result.get("expanded_query") or query
        key_terms = result.get("key_terms") or []
        return {"intent": intent, "expanded_query": expanded, "key_terms": key_terms}
    except Exception:
        return {"intent": "targeted", "expanded_query": query, "key_terms": []}


async def _retrieve_context(
    session,
    search_query: str,
    gemini: GeminiClient,
    tree_search: TreeSearchService,
    ai_provider: str,
    intent: str,
    expanded_query: str,
    key_terms: list,
) -> tuple:
    """
    3-tier retrieval with explicit confidence.
    Tier 1: BM25 chunk search over expanded_query (intent-aware top_k)
    Tier 2: LLM tree search (if BM25 is low and HTOC exists)
    Tier 3: Full-text fallback (no index yet)

    Returns (context, source_sections, retrieval_confidence, use_fulltext)
    """
    bm25 = _get_bm25_service(session)
    has_bm25 = bm25._index is not None

    if has_bm25 and session.page_texts:
        # Tier 1: BM25 chunk search with synonym-expanded query + key_terms boost
        search_result = bm25.search(
            expanded_query, session.page_texts, intent=intent, key_terms=key_terms
        )
        confidence = search_result.get("confidence", "low")

        if confidence == "low" and session.htoc_tree:
            # Tier 2: LLM tree search
            logger.info("BM25 low confidence, falling back to LLM tree search")
            try:
                tree_result = await tree_search.search(
                    tree=session.htoc_tree,
                    query=search_query,
                    page_texts=session.page_texts,
                    gemini_client=gemini,
                    provider=ai_provider,
                )
                search_result = tree_result
                confidence = "medium"  # tree search is used, mark as medium
            except Exception as e:
                logger.warning("LLM tree search failed: %s — keeping BM25 result", e)

        if confidence == "low" and not session.htoc_tree:
            # Tier 3: No tree available, BM25 was low — still use BM25 but flag it
            logger.info("Low confidence BM25 with no HTOC tree — returning result with low confidence flag")

        context = search_result["context"]
        source_sections = search_result.get("source_sections", [])
        source_info = ", ".join(
            "{} (p.{})".format(s["title"], s["pages"]) for s in source_sections
        )
        logger.info("Retrieved %d sections (confidence=%s): %s", len(source_sections), confidence, source_info)
        return context, source_sections, confidence, False

    # No BM25 index at all (HTOC still building) — full-text fallback
    return None, [], "low", True


# ──────────────────────────────────────────────────────────────────────
#  NON-STREAMING CHAT
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

    status = getattr(session, 'htoc_status', None) or 'pending'
    if not session.anonymized_text and status in ("processing",):
        raise HTTPException(202, "Document is still being processed. Please wait a few seconds.")

    # 2. Anonymize question + history
    anonymized_question, _ = await pii_service.anonymize(request.message)
    anonymized_history = []
    for msg in request.history:
        anonymized_content, _ = await pii_service.anonymize(msg.content)
        anonymized_history.append({"role": msg.role, "content": anonymized_content})

    # 3. Check response cache
    query_hash = compute_query_hash(session_id, anonymized_question)
    cached = await session_service.get_cached_chat(session_id, query_hash)
    if cached:
        final_response = pii_service.deanonymize(cached["response"], session.pii_mapping)
        return ChatResponse(
            response=final_response,
            source_sections=cached.get("source_sections"),
            retrieval_confidence=cached.get("retrieval_confidence"),
        )

    # 4. Trim history (token-budget based)
    trimmed_history = _trim_history(anonymized_history)
    ai_provider = getattr(session, "ai_provider", None) or "gemini"

    # 5. Single query understanding call: intent + synonym expansion + key terms
    search_query = _build_search_query(anonymized_question, anonymized_history)
    understood = await _understand_query(anonymized_question, gemini, ai_provider)
    intent = understood["intent"]
    expanded_query = _build_search_query(understood["expanded_query"], anonymized_history)
    key_terms = understood["key_terms"]
    logger.info("Query intent=%s expanded=%s", intent, understood["expanded_query"][:80])

    # 6. 3-tier retrieval
    context, source_sections, retrieval_confidence, use_fulltext = await _retrieve_context(
        session, search_query, gemini, tree_search, ai_provider, intent, expanded_query, key_terms
    )

    # 7. Generate response
    if use_fulltext:
        try:
            anonymized_response = await gemini.chat(
                anonymized_question,
                session.anonymized_text,
                trimmed_history,
                provider=ai_provider,
            )
        except Exception as e:
            logger.error("Chat failed: %s", e)
            raise HTTPException(500, "Chat failed. Please try again.")
    else:
        source_info = ", ".join(
            "{} (p.{})".format(s["title"], s["pages"]) for s in source_sections
        )
        anonymized_response = await gemini.chat_with_context(
            question=anonymized_question,
            context=context,
            chat_history=trimmed_history,
            source_info=source_info,
            provider=ai_provider,
        )

    # 8. De-anonymize response
    final_response = pii_service.deanonymize(anonymized_response, session.pii_mapping)

    # 9. Cache the response
    try:
        await session_service.cache_chat_response(
            session_id, query_hash, anonymized_response,
            source_sections if source_sections else [],
            retrieval_confidence=retrieval_confidence,
        )
    except Exception:
        pass

    return ChatResponse(
        response=final_response,
        source_sections=source_sections if source_sections else None,
        retrieval_confidence=retrieval_confidence if (use_fulltext or retrieval_confidence == "low") else None,
    )


# ──────────────────────────────────────────────────────────────────────
#  STREAMING CHAT (SSE)
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
      - event: token      → data: {"text": "chunk of response"}
      - event: sources    → data: {"source_sections": [...], "retrieval_confidence": "..."}
      - event: done       → data: {}
      - event: error      → data: {"error": "message"}
    """
    # 1. Retrieve session
    session = await session_service.get_for_user(session_id, current_user)
    if not session:
        raise HTTPException(404, "Session expired or not found")

    status = getattr(session, 'htoc_status', None) or 'pending'
    if not session.anonymized_text and status in ("processing",):
        raise HTTPException(202, "Document is still being processed. Please wait a few seconds.")

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
        async def cached_stream():
            final = pii_service.deanonymize(cached["response"], session.pii_mapping)
            yield f"event: token\ndata: {json.dumps({'text': final})}\n\n"
            if cached.get("source_sections"):
                yield f"event: sources\ndata: {json.dumps({'source_sections': cached['source_sections'], 'retrieval_confidence': cached.get('retrieval_confidence')})}\n\n"
            yield "event: done\ndata: {}\n\n"

        return StreamingResponse(cached_stream(), media_type="text/event-stream")

    # 4. Trim history (P7)
    trimmed_history = _trim_history(anonymized_history)
    ai_provider = getattr(session, "ai_provider", None) or "gemini"

    # 5. Intent + retrieval
    search_query = _build_search_query(anonymized_question, anonymized_history)
    understood = await _understand_query(anonymized_question, gemini, ai_provider)
    intent = understood["intent"]
    expanded_query = _build_search_query(understood["expanded_query"], anonymized_history)
    key_terms = understood["key_terms"]
    logger.info("Query intent=%s expanded=%s", intent, understood["expanded_query"][:80])

    context, source_sections, retrieval_confidence, use_fulltext = await _retrieve_context(
        session, search_query, gemini, tree_search, ai_provider, intent, expanded_query, key_terms
    )

    source_info = ", ".join(
        "{} (p.{})".format(s["title"], s["pages"]) for s in source_sections
    )

    # 6. Stream response
    async def event_stream():
        full_response_parts = []
        buffer = ""

        try:
            # Send sources first so frontend can display them immediately
            if source_sections:
                yield f"event: sources\ndata: {json.dumps({'source_sections': source_sections, 'retrieval_confidence': retrieval_confidence if retrieval_confidence == 'low' else None})}\n\n"
            elif use_fulltext or retrieval_confidence == "low":
                yield f"event: sources\ndata: {json.dumps({'source_sections': [], 'retrieval_confidence': 'low'})}\n\n"

            # Stream LLM response
            if context and not use_fulltext:
                stream = gemini.chat_with_context_stream(
                    question=anonymized_question,
                    context=context,
                    chat_history=trimmed_history,
                    source_info=source_info,
                    provider=ai_provider,
                )
            else:
                stream = gemini.chat_stream(
                    anonymized_question,
                    session.anonymized_text,
                    trimmed_history,
                    provider=ai_provider,
                )

            async for chunk in stream:
                full_response_parts.append(chunk)
                buffer += chunk

                partial = _PARTIAL_TOKEN_RE.search(buffer)
                if partial:
                    emit = buffer[:partial.start()]
                    buffer = buffer[partial.start():]
                else:
                    emit = buffer
                    buffer = ""

                if emit:
                    clean_chunk = pii_service.deanonymize(emit, session.pii_mapping)
                    yield f"event: token\ndata: {json.dumps({'text': clean_chunk})}\n\n"

            if buffer:
                clean_chunk = pii_service.deanonymize(buffer, session.pii_mapping)
                yield f"event: token\ndata: {json.dumps({'text': clean_chunk})}\n\n"

            yield "event: done\ndata: {}\n\n"

            full_anonymized = "".join(full_response_parts)
            try:
                await session_service.cache_chat_response(
                    session_id, query_hash, full_anonymized,
                    source_sections if source_sections else [],
                    retrieval_confidence=retrieval_confidence,
                )
            except Exception:
                pass

        except Exception as e:
            logger.error("Stream error: %s", e)
            yield f"event: error\ndata: {json.dumps({'error': 'An error occurred during streaming. Please try again.'})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
