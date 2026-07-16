"""
BM25 Hybrid Search Service.

Uses BM25 scoring over paragraph-level chunks (not full pages) boosted by HTOC
section summaries. Each chunk carries exact page_idx so source citations point to
the specific page, not a broad section range.

- BM25 handles keyword matching over ~paragraph-sized chunks
- HTOC summaries provide token-overlap boost (semantic boost added in P2 via embeddings)
- Zero API calls, <10ms per query, works on 300+ page docs
"""

import re
import hashlib
import logging
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Maximum context to extract (in characters)
MAX_CONTEXT_CHARS = 50000

# HTOC token-overlap fallback boost multipliers (used when embeddings are unavailable)
HTOC_TITLE_BOOST_FALLBACK = 3.0
HTOC_SUMMARY_BOOST_FALLBACK = 1.5


def _get_thresholds():
    """Load BM25 thresholds from config (so they can be updated without restarting)."""
    try:
        from app.core.config import settings
        return settings.BM25_LOW_THRESHOLD, settings.BM25_HIGH_THRESHOLD
    except Exception:
        return 0.5, 2.0


def _tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    text = text.lower()
    text = re.sub(r'[^\w\s₹]', ' ', text)
    tokens = text.split()
    return [t for t in tokens if len(t) > 2]


class BM25SearchService:
    """
    Fast local search using BM25 over paragraph chunks + HTOC summary boost.
    Built once at upload, stored in session, used for every chat query.
    """

    def __init__(self):
        self._index: Optional[BM25Okapi] = None
        self._chunks: List[Dict[str, Any]] = []          # {chunk_id, page_idx, char_start, char_end, text}
        self._chunk_tokens: List[List[str]] = []         # parallel to _chunks
        self._htoc_nodes: List[Dict[str, Any]] = []      # flat list from HTOC tree
        self._page_to_nodes: Dict[int, List[Dict]] = {}  # page_idx -> [nodes covering that page]
        self._num_pages: int = 0

    def build_index(
        self,
        page_texts: List[str],
        htoc_tree: Optional[Dict] = None,
        page_chunks: Optional[List[Dict]] = None,
    ):
        """
        Build BM25 index from paragraph chunks + extract HTOC node metadata for boosting.
        Called once at upload time.

        page_chunks: pre-built chunk list from document_parser. If None, falls back to
                     indexing full pages (one chunk per page) for backwards compatibility.
        """
        self._num_pages = len(page_texts)

        # Use provided chunks; fall back to one-chunk-per-page
        if page_chunks:
            self._chunks = page_chunks
        else:
            self._chunks = [
                {
                    "chunk_id": f"p{i}_c0",
                    "page_idx": i,
                    "char_start": 0,
                    "char_end": len(text),
                    "text": text,
                }
                for i, text in enumerate(page_texts)
            ]

        # Tokenize each chunk for BM25
        self._chunk_tokens = [_tokenize(c["text"]) for c in self._chunks]

        # BM25Okapi divides by average document length internally — an all-empty
        # corpus (e.g. text extraction returned nothing) makes that average 0
        # and raises ZeroDivisionError. Skip index construction in that case.
        if self._chunk_tokens and any(self._chunk_tokens):
            self._index = BM25Okapi(self._chunk_tokens)

        # Extract flat node list from HTOC tree for keyword boost
        if htoc_tree:
            self._htoc_nodes = self._flatten_tree(htoc_tree)
            self._build_page_node_map()

    def search(
        self,
        query: str,
        page_texts: List[str],
        top_k: int = 8,
        intent: str = "targeted",
        key_terms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Search for relevant chunks using BM25 + HTOC boost + key_terms priority boost.

        intent: "targeted" (default, top_k=8), "exhaustive" (top_k=15), "comparative" (top_k=10)
        key_terms: high-priority tokens from query understanding — chunks containing these get a boost

        Returns:
        {
            "context": "extracted text from top chunks",
            "source_sections": [{"title": "...", "pages": "1-3", "page_start": 1, "page_end": 3, "node_id": "0001"}],
            "reasoning": "...",
            "confidence": "high|medium|low",
        }
        """
        # Apply intent-based top_k (no hardcoded string matching)
        if intent == "exhaustive":
            top_k = max(top_k, 15)
        elif intent == "comparative":
            top_k = max(top_k, 10)

        if not self._index or not page_texts:
            return {
                "context": "\n\n".join(page_texts[:3]) if page_texts else "",
                "source_sections": [],
                "reasoning": "No index available, returning first pages",
                "confidence": "low",
            }

        query_tokens = _tokenize(query)
        if not query_tokens:
            return {
                "context": "\n\n".join(page_texts[:3]) if page_texts else "",
                "source_sections": [],
                "reasoning": "Empty query after tokenization",
                "confidence": "low",
            }

        low_threshold, high_threshold = _get_thresholds()

        # Step 1: BM25 scores for each chunk
        bm25_scores = self._index.get_scores(query_tokens)

        # Step 1b: key_terms priority boost — chunks containing exact key terms score higher
        # key_terms come from the LLM query-understanding call (most important tokens in query)
        if key_terms:
            key_term_set = set(t.lower() for t in key_terms if t)
            for chunk_idx, chunk_tokens in enumerate(self._chunk_tokens):
                chunk_token_set = set(chunk_tokens)
                hits = len(key_term_set & chunk_token_set)
                if hits:
                    bm25_scores[chunk_idx] += hits * 0.5  # 0.5 per key_term hit

        # Step 2: HTOC title/summary token-overlap boost
        boosted_scores = list(bm25_scores)
        if self._htoc_nodes:
            query_set = set(query_tokens)
            seen_node_boost: dict = {}

            for chunk_idx, chunk in enumerate(self._chunks):
                page_idx = chunk["page_idx"]
                nodes = self._page_to_nodes.get(page_idx, [])
                for node in nodes:
                    nid = node.get("node_id", "")
                    if nid in seen_node_boost:
                        boosted_scores[chunk_idx] += seen_node_boost[nid]
                        continue

                    title_tokens = set(_tokenize(node.get("title", "")))
                    summary_tokens = set(_tokenize(node.get("summary", "")))
                    title_overlap = len(query_set & title_tokens) / max(len(query_set), 1)
                    summary_overlap = len(query_set & summary_tokens) / max(len(query_set), 1)
                    boost = (title_overlap * HTOC_TITLE_BOOST_FALLBACK) + (summary_overlap * HTOC_SUMMARY_BOOST_FALLBACK)
                    seen_node_boost[nid] = boost
                    boosted_scores[chunk_idx] += boost

        # Step 3: Rank chunks by boosted score
        scored_chunks = sorted(
            enumerate(boosted_scores),
            key=lambda x: x[1],
            reverse=True,
        )

        max_score = scored_chunks[0][1] if scored_chunks else 0
        confidence = "high" if max_score > high_threshold else (
            "medium" if max_score > low_threshold else "low"
        )

        # Step 4: Select top chunks, expanding to full HTOC sections for matched nodes
        selected_chunk_idxs = set()
        selected_pages = set()
        source_sections = []
        seen_nodes = set()

        for chunk_idx, score in scored_chunks:
            if len(selected_chunk_idxs) >= top_k * 3:
                break
            if score < low_threshold and len(selected_chunk_idxs) >= top_k:
                break

            chunk = self._chunks[chunk_idx]
            page_idx = chunk["page_idx"]
            selected_chunk_idxs.add(chunk_idx)
            selected_pages.add(page_idx)

            # Find HTOC node for this page — expand selection to all chunks in that node's range
            nodes = self._page_to_nodes.get(page_idx, [])
            for node in nodes:
                nid = node.get("node_id", "")
                if nid and nid not in seen_nodes:
                    seen_nodes.add(nid)
                    start = node.get("start_page", page_idx)
                    end = min(node.get("end_page", page_idx), self._num_pages - 1)  # bounds check

                    # Include all chunks in this node's page range
                    for ci, c in enumerate(self._chunks):
                        if start <= c["page_idx"] <= end:
                            selected_chunk_idxs.add(ci)
                            selected_pages.add(c["page_idx"])

                    # Build page range for display (1-indexed)
                    page_start_1 = start + 1
                    page_end_1 = end + 1
                    page_range = f"{page_start_1}-{page_end_1}" if start != end else str(page_start_1)
                    source_sections.append({
                        "title": node.get("title", f"Page {page_idx + 1}"),
                        "pages": page_range,
                        "page_start": page_start_1,
                        "page_end": page_end_1,
                        "node_id": nid,
                    })

        # If no HTOC nodes matched, emit a bare page citation for the top chunk
        if not source_sections and scored_chunks:
            top_chunk = self._chunks[scored_chunks[0][0]]
            p = top_chunk["page_idx"]
            source_sections.append({
                "title": f"Page {p + 1}",
                "pages": str(p + 1),
                "page_start": p + 1,
                "page_end": p + 1,
                "node_id": "",
            })

        # Step 5: Build context from selected chunks in page order
        # Sort by (page_idx, char_start) to maintain document order
        ordered_chunks = sorted(
            [self._chunks[i] for i in selected_chunk_idxs],
            key=lambda c: (c["page_idx"], c["char_start"]),
        )

        context_parts = []
        total_chars = 0
        last_page = -1
        for chunk in ordered_chunks:
            p = chunk["page_idx"]
            if p != last_page:
                nodes = self._page_to_nodes.get(p, [])
                section_title = nodes[0].get("title", "Section") if nodes else "Section"
                header = f"[Page {p + 1} — {section_title}]"
                last_page = p
            else:
                header = ""

            chunk_text = (header + "\n" + chunk["text"]) if header else chunk["text"]
            if total_chars + len(chunk_text) > MAX_CONTEXT_CHARS:
                remaining = MAX_CONTEXT_CHARS - total_chars
                if remaining > 200:
                    # Truncate at sentence boundary
                    truncated = chunk_text[:remaining]
                    last_period = max(truncated.rfind('. '), truncated.rfind('.\n'))
                    if last_period > remaining * 0.8:
                        truncated = truncated[:last_period + 1]
                    context_parts.append(truncated + "\n[Content truncated]")
                break
            context_parts.append(chunk_text)
            total_chars += len(chunk_text)

        context = "\n\n".join(context_parts)

        return {
            "context": context,
            "source_sections": source_sections[:top_k],
            "reasoning": f"BM25 chunk search (confidence: {confidence}, top_score: {max_score:.2f}, chunks: {len(selected_chunk_idxs)})",
            "confidence": confidence,
            "max_score": max_score,
        }

    async def search_async(
        self,
        query: str,
        page_texts: List[str],
        top_k: int = 8,
        intent: str = "targeted",
        key_terms: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Async shim — delegates to sync search(). Kept for interface compatibility."""
        return self.search(query, page_texts, top_k=top_k, intent=intent, key_terms=key_terms)

    def get_serializable_data(self) -> Dict[str, Any]:
        """Return data needed to reconstruct the index from MongoDB."""
        return {
            "htoc_nodes": self._htoc_nodes,
            "chunk_tokens": self._chunk_tokens,
            "chunks": self._chunks,
            "num_pages": self._num_pages,
        }

    def load_from_data(self, data: Dict[str, Any]):
        """Reconstruct index from stored data (loaded from MongoDB)."""
        self._htoc_nodes = data.get("htoc_nodes", [])
        self._num_pages = data.get("num_pages", 0)
        self._chunks = data.get("chunks", [])
        self._chunk_tokens = data.get("chunk_tokens", [])

        # Legacy sessions stored page_tokens instead of chunk_tokens — migrate transparently
        if not self._chunk_tokens and "page_tokens" in data:
            self._chunk_tokens = data["page_tokens"]
            # Reconstruct chunk list as one-per-page if missing
            if not self._chunks:
                self._chunks = [
                    {"chunk_id": f"p{i}_c0", "page_idx": i, "char_start": 0, "char_end": 0, "text": ""}
                    for i in range(self._num_pages)
                ]

        if self._chunk_tokens:
            self._index = BM25Okapi(self._chunk_tokens)
        self._build_page_node_map()

    def _flatten_tree(self, node: Dict, result: List = None) -> List[Dict]:
        """Flatten HTOC tree to a list of {node_id, title, summary, start_page, end_page}."""
        if result is None:
            result = []

        result.append({
            "node_id": node.get("node_id", ""),
            "title": node.get("title", ""),
            "summary": node.get("summary", ""),
            "start_page": node.get("start_page", 0),
            "end_page": node.get("end_page", 0),
        })
        for child in node.get("children", []):
            self._flatten_tree(child, result)

        return result

    def _build_page_node_map(self):
        """Build a map of page_idx -> [nodes covering that page], bounds-checked."""
        self._page_to_nodes = {}
        for node in self._htoc_nodes:
            start = node.get("start_page", 0)
            end = min(node.get("end_page", start), self._num_pages - 1)  # clamp to valid range
            for p in range(start, end + 1):
                if p not in self._page_to_nodes:
                    self._page_to_nodes[p] = []
                self._page_to_nodes[p].append(node)

        # Prefer most specific (smallest range) node per page
        for p in self._page_to_nodes:
            self._page_to_nodes[p].sort(
                key=lambda n: n.get("end_page", 0) - n.get("start_page", 0)
            )


def compute_query_hash(session_id: str, question: str) -> str:
    """Hash for response caching. Normalizes question before hashing."""
    normalized = re.sub(r'\s+', ' ', question.strip().lower())
    return hashlib.md5(f"{session_id}:{normalized}".encode()).hexdigest()
