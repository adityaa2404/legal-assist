"""
Embedding Service for semantic HTOC boost.

Uses Gemini gemini-embedding-001 via the google-genai SDK (already installed).
Replaces the token-overlap boost in BM25SearchService with cosine similarity,
so queries like "counterparty responsibilities" match "Party Obligations" sections.

Batches in groups of 100 to respect API rate limits.
Falls back to an empty embedding on failure so BM25 still works without semantics.
"""

import logging
import math
from typing import List, Optional
from google import genai
from google.genai import types as genai_types
from app.core.config import settings

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "gemini-embedding-001"
BATCH_SIZE = 100


def _get_client() -> genai.Client:
    return genai.Client(api_key=settings.GEMINI_API_KEY)


async def embed_texts(texts: List[str]) -> List[Optional[List[float]]]:
    """
    Embed a list of texts using Gemini gemini-embedding-001.
    Returns a list of float vectors (same length as input).
    Returns None for any text that fails to embed.
    """
    if not texts:
        return []

    client = _get_client()
    results: List[Optional[List[float]]] = [None] * len(texts)

    for batch_start in range(0, len(texts), BATCH_SIZE):
        batch = texts[batch_start:batch_start + BATCH_SIZE]
        batch_indices = list(range(batch_start, batch_start + len(batch)))
        try:
            response = await client.aio.models.embed_content(
                model=EMBEDDING_MODEL,
                contents=batch,
                config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_DOCUMENT"),
            )
            for i, embedding in enumerate(response.embeddings):
                results[batch_indices[i]] = embedding.values
        except Exception as e:
            logger.warning("Embedding batch %d-%d failed: %s", batch_start, batch_start + len(batch), e)
            # Leave as None — caller handles fallback

    return results


async def embed_query(text: str) -> Optional[List[float]]:
    """Embed a single query string for retrieval."""
    client = _get_client()
    try:
        response = await client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=[text],
            config=genai_types.EmbedContentConfig(task_type="RETRIEVAL_QUERY"),
        )
        return response.embeddings[0].values
    except Exception as e:
        logger.warning("Query embedding failed: %s", e)
        return None


def cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(x * x for x in b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)
