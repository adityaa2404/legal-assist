""""Codiv/OpenJev adapter for bounded legal-query intent classification.

Query expansion and key-term extraction remain with the existing Gemini call.
Failures return None so the caller can retain Gemini's intent.
"""
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

CODIV_SYSTEMONE_URL = "https://api.codiv.ai/v1/systemone"
CODIV_MODEL = "openjev-latest"
QUERY_INTENTS = {"exhaustive", "comparative", "targeted"}


def parse_intent_response(payload: Any) -> Optional[str]:
    """Return a supported intent from a Codiv response, or None for malformed output."""
    try:
        intent = payload["answers"]["query_intent"]["choice"]
    except (KeyError, TypeError):
        return None
    return intent if isinstance(intent, str) and intent in QUERY_INTENTS else None


async def classify_query_intent(
    query: str,
    api_key: Optional[str],
    *,
    timeout_seconds: float = 8.0,
) -> Optional[str]:
    """Classify query intent through Codiv. None tells the caller to use its fallback."""
    if not api_key or not query.strip():
        return None

    payload = {
        "model": CODIV_MODEL,
        "state": query,
        "questions": {
            "query_intent": {
                "type": "choice",
                "instructions": (
                    "Classify the user's legal-document search query by retrieval intent. "
                    "Choose exhaustive when the user requests comprehensive coverage, all "
                    "items, every clause, or a complete list. Choose comparative when the "
                    "user asks to compare two or more things. Choose targeted when the user "
                    "asks for one specific fact or answer. Classify the request, not its subject."
                ),
                "criteria": {
                    "exhaustive": "Comprehensive coverage, all items, every clause, or a complete list.",
                    "comparative": "Compare two or more items, clauses, parties, or alternatives.",
                    "targeted": "One specific fact, clause, obligation, date, or answer.",
                },
            }
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                CODIV_SYSTEMONE_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            intent = parse_intent_response(response.json())
            if intent is None:
                logger.warning("Codiv returned an invalid intent response; using Gemini fallback")
            return intent
    except Exception as exc:
        # Never log request headers or the API key.
        logger.warning(
            "Codiv query-intent classification failed; using Gemini fallback (%s)",
            type(exc).__name__,
        )
        return None
