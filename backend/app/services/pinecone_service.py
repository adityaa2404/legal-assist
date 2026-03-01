from pinecone import Pinecone
from google import genai
from google.genai import types
from app.core.config import settings
from typing import List, Dict, Any
import logging

# Use v1 API for text-embedding-004 (not available on v1beta)
_genai_client = genai.Client(
    api_key=settings.GEMINI_API_KEY,
    http_options=types.HttpOptions(api_version='v1'),
)

EMBEDDING_MODEL = "text-embedding-004"


class PineconeService:
    def __init__(self):
        pc = Pinecone(api_key=settings.PINECONE_API_KEY)
        self.index = pc.Index(settings.PINECONE_INDEX_NAME)

    async def get_references(self, clause_texts: List[str], top_k: int = 3) -> List[List[Dict[str, Any]]]:
        """
        For each clause text, embed it and query Pinecone for the top-k
        most similar rulebook entries. Returns a list of reference lists,
        one per clause.
        """
        if not clause_texts:
            return []

        results = []
        for text in clause_texts:
            try:
                refs = await self._query_single(text, top_k)
                results.append(refs)
            except Exception as e:
                logging.error(f"Pinecone query failed for clause: {e}")
                results.append([])

        return results

    async def _query_single(self, text: str, top_k: int) -> List[Dict[str, Any]]:
        """Embed a single clause and query Pinecone."""
        # Generate embedding using google-genai
        embed_response = await _genai_client.aio.models.embed_content(
            model=EMBEDDING_MODEL,
            contents=text,
        )

        vector = embed_response.embeddings[0].values

        # Query Pinecone (sync client — runs fast, no async needed)
        query_result = self.index.query(
            vector=vector,
            top_k=top_k,
            include_metadata=True,
        )

        references = []
        for match in query_result.matches:
            ref_text = match.metadata.get("text", "") if match.metadata else ""
            references.append({
                "text": ref_text,
                "score": round(float(match.score), 4),
            })

        return references
