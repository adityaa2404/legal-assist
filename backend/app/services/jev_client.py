"""Small, opt-in Jev adapter for bounded query-intent classification.

The rest of query understanding (legal synonym expansion and key-term extraction)
remains with the existing LLM. Any Jev failure returns None so callers can retain
their existing classification rather than breaking chat.
"""
import logging
from typing import Any, Optional

import httpx

logger = logging.getLogger(__name__)

JEV_DECISIONS_URL = "https://jev-api.org/api/v1/decisions"
JEV_MODEL = "jev-1.13"
QUERY_INTENTS = {"exhaustive", "comparative", "targeted"}


def parse_intent_response(payload: dict[str, Any]) -> Optional[str]:
    """Return a supported intent from a Jev response, or None for malformed output."""
    try:
        intent = payload["answers"]["query_intent"]["choice"]
    except (KeyError, TypeError):
        return None
    return intent if intent in QUERY_INTENTS else None


async def classify_query_intent(
    query: str,
    api_key: Optional[str],
    *,
    timeout_seconds: float = 8.0,
) -> Optional[str]:
    """Classify retrieval intent with Jev. None means the caller should fall back."""
    if not api_key or not query.strip():
        return None

    payload = {
        "model": JEV_MODEL,
        "state": query,
        "questions": {
            "query_intent": {
                "type": "choice",
                "instructions": (
                    "Classify the user's legal-document search query by retrieval intent. "
                    "Choose exhaustive when the user requests all items, every clause, "
                    "or a complete list. Choose comparative when the user asks to compare "
                    "two or more things. Choose targeted when the user asks for one specific "
                    "fact or answer. Classify the request, not its subject matter."
                ),
                "criteria": {
                    "exhaustive": "Requests comprehensive coverage, all items, every clause, or a complete list.",
                    "comparative": "Explicitly compares two or more items, clauses, parties, or alternatives.",
                    "targeted": "Requests one specific fact, clause, obligation, date, or answer.",
                },
            }
        },
    }

    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            response = await client.post(
                JEV_DECISIONS_URL,
                headers={"Authorization": f"Bearer {api_key}"},
                json=payload,
            )
            response.raise_for_status()
            intent = parse_intent_response(response.json())
            if intent is None:
                logger.warning("Jev returned an invalid query-intent response; using LLM fallback")
            return intent
    except Exception as exc:
        # Do not log request headers or the API key.
        logger.warning("Jev query-intent classification failed; using LLM fallback (%s)", type(exc).__name__)
        return None
