"""
BM25 Hybrid Search Service.

Replaces LLM-based tree search for chat with a fast, free, local keyword search.
Uses BM25 scoring boosted by HTOC section summaries for best-of-both-worlds retrieval.

- BM25 handles keyword matching (~80% of legal queries)
- HTOC summaries provide semantic boost (section titles/summaries match conceptual queries)
- Zero API calls, <5ms per query, works on 300+ page docs
"""

import re
import hashlib
import logging
from typing import List, Dict, Any, Optional
from rank_bm25 import BM25Okapi

logger = logging.getLogger(__name__)

# Maximum context to extract (in characters)
MAX_CONTEXT_CHARS = 50000

# BM25 score threshold — below this, results are likely irrelevant
LOW_SCORE_THRESHOLD = 0.5


def _tokenize(text: str) -> List[str]:
    """Simple whitespace + punctuation tokenizer for BM25."""
    text = text.lower()
    # Remove common legal boilerplate words that add noise
    text = re.sub(r'[^\w\s₹]', ' ', text)
    tokens = text.split()
    # Remove very short tokens (articles, prepositions)
    return [t for t in tokens if len(t) > 2]


class BM25SearchService:
    """
    Fast local search using BM25 + HTOC summary boost.
    Built once at upload, stored in session, used for every chat query.
    """

    def __init__(self):
        self._index: Optional[BM25Okapi] = None
        self._page_tokens: List[List[str]] = []
        self._htoc_nodes: List[Dict[str, Any]] = []  # flat list: [{node_id, title, summary, start_page, end_page}]
        self._page_to_nodes: Dict[int, List[Dict]] = {}  # page_idx -> [nodes covering this page]
        self._num_pages: int = 0

    def build_index(self, page_texts: List[str], htoc_tree: Optional[Dict] = None):
        """
        Build BM25 index from page texts + extract HTOC node metadata for boosting.
        Called once at upload time. ~10-50ms for 300 pages.
        """
        self._num_pages = len(page_texts)

        # Tokenize each page for BM25
        self._page_tokens = [_tokenize(text) for text in page_texts]

        # Build BM25 index
        if self._page_tokens:
            self._index = BM25Okapi(self._page_tokens)

        # Extract flat node list from HTOC tree for keyword boost
        if htoc_tree:
            self._htoc_nodes = self._flatten_tree(htoc_tree)
            self._build_page_node_map()

    def search(
        self,
        query: str,
        page_texts: List[str],
        top_k: int = 5,
    ) -> Dict[str, Any]:
        """
        Search for relevant pages using BM25 + HTOC boost.

        Returns same format as TreeSearchService.search() for drop-in compatibility:
        {
            "context": "extracted text from top pages",
            "source_sections": [{"title": "...", "pages": "1-3", "node_id": "0001"}],
            "reasoning": "BM25 hybrid search"
        }
        """
        if not self._index or not page_texts:
            return {
                "context": "\n\n".join(page_texts[:3]) if page_texts else "",
                "source_sections": [],
                "reasoning": "No index available, returning first pages",
            }

        query_tokens = _tokenize(query)
        if not query_tokens:
            return {
                "context": "\n\n".join(page_texts[:3]) if page_texts else "",
                "source_sections": [],
                "reasoning": "Empty query after tokenization",
            }

        # Step 1: BM25 scores for each page
        bm25_scores = self._index.get_scores(query_tokens)

        # Step 2: HTOC summary boost — if a page's section title/summary matches query terms, boost it
        boosted_scores = list(bm25_scores)
        if self._htoc_nodes:
            query_lower = " ".join(query_tokens)
            for page_idx in range(self._num_pages):
                nodes = self._page_to_nodes.get(page_idx, [])
                for node in nodes:
                    # Check title and summary match
                    title_tokens = set(_tokenize(node.get("title", "")))
                    summary_tokens = set(_tokenize(node.get("summary", "")))
                    query_set = set(query_tokens)

                    # Boost by overlap ratio
                    title_overlap = len(query_set & title_tokens) / max(len(query_set), 1)
                    summary_overlap = len(query_set & summary_tokens) / max(len(query_set), 1)

                    # Boost: up to 3.0 for title match, 1.5 for summary match
                    boost = (title_overlap * 3.0) + (summary_overlap * 1.5)
                    boosted_scores[page_idx] += boost

        # Step 3: Rank pages by boosted score
        scored_pages = sorted(
            enumerate(boosted_scores),
            key=lambda x: x[1],
            reverse=True,
        )

        # Step 4: Select top pages, grouping by HTOC sections
        selected_pages = set()
        source_sections = []
        seen_nodes = set()
        max_score = scored_pages[0][1] if scored_pages else 0

        for page_idx, score in scored_pages:
            if len(selected_pages) >= top_k * 3:  # allow more pages since sections span multiple
                break
            if score < LOW_SCORE_THRESHOLD and len(selected_pages) >= top_k:
                break

            selected_pages.add(page_idx)

            # Find HTOC node for this page and add to source_sections
            nodes = self._page_to_nodes.get(page_idx, [])
            for node in nodes:
                nid = node.get("node_id", "")
                if nid and nid not in seen_nodes:
                    seen_nodes.add(nid)
                    start = node.get("start_page", page_idx)
                    end = node.get("end_page", page_idx)
                    # Include all pages from this section
                    for p in range(start, min(end + 1, len(page_texts))):
                        selected_pages.add(p)
                    page_range = f"{start + 1}-{end + 1}" if start != end else str(start + 1)
                    source_sections.append({
                        "title": node.get("title", f"Page {page_idx + 1}"),
                        "pages": page_range,
                        "node_id": nid,
                    })

        # Step 5: Build context from selected pages (sorted by page order)
        context_parts = []
        for page_idx in sorted(selected_pages):
            if page_idx < len(page_texts):
                # Find best matching node title for this page
                nodes = self._page_to_nodes.get(page_idx, [])
                section_title = nodes[0].get("title", "Section") if nodes else "Section"
                context_parts.append(
                    f"[Page {page_idx + 1} — {section_title}]\n{page_texts[page_idx]}"
                )

        context = "\n\n".join(context_parts)

        # Truncate at sentence boundary if too long
        if len(context) > MAX_CONTEXT_CHARS:
            truncated = context[:MAX_CONTEXT_CHARS]
            last_period = max(truncated.rfind('. '), truncated.rfind('.\n'))
            if last_period > MAX_CONTEXT_CHARS * 0.8:
                truncated = truncated[:last_period + 1]
            context = truncated + "\n\n[Note: Some content was truncated due to length.]"

        # If all scores are very low, flag it for potential LLM fallback
        confidence = "high" if max_score > 2.0 else ("medium" if max_score > LOW_SCORE_THRESHOLD else "low")

        return {
            "context": context,
            "source_sections": source_sections[:top_k],
            "reasoning": f"BM25 hybrid search (confidence: {confidence}, top_score: {max_score:.2f})",
            "confidence": confidence,
            "max_score": max_score,
        }

    def get_serializable_data(self) -> Dict[str, Any]:
        """
        Return data needed to reconstruct the index from MongoDB.
        We store the HTOC nodes and page token lists — BM25 index is rebuilt from tokens.
        """
        return {
            "htoc_nodes": self._htoc_nodes,
            "page_tokens": self._page_tokens,
            "num_pages": self._num_pages,
        }

    def load_from_data(self, data: Dict[str, Any]):
        """Reconstruct index from stored data (loaded from MongoDB)."""
        self._htoc_nodes = data.get("htoc_nodes", [])
        self._page_tokens = data.get("page_tokens", [])
        self._num_pages = data.get("num_pages", 0)

        if self._page_tokens:
            self._index = BM25Okapi(self._page_tokens)
        self._build_page_node_map()

    def _flatten_tree(self, node: Dict, result: List = None) -> List[Dict]:
        """Flatten HTOC tree to a list of {node_id, title, summary, start_page, end_page}."""
        if result is None:
            result = []

        if not node.get("children"):
            # Leaf node — this is what we index
            result.append({
                "node_id": node.get("node_id", ""),
                "title": node.get("title", ""),
                "summary": node.get("summary", ""),
                "start_page": node.get("start_page", 0),
                "end_page": node.get("end_page", 0),
            })
        else:
            # Also add parent for broad queries
            result.append({
                "node_id": node.get("node_id", ""),
                "title": node.get("title", ""),
                "summary": node.get("summary", ""),
                "start_page": node.get("start_page", 0),
                "end_page": node.get("end_page", 0),
            })
            for child in node["children"]:
                self._flatten_tree(child, result)

        return result

    def _build_page_node_map(self):
        """Build a map of page_idx -> [nodes covering that page]."""
        self._page_to_nodes = {}
        for node in self._htoc_nodes:
            start = node.get("start_page", 0)
            end = node.get("end_page", start)
            for p in range(start, end + 1):
                if p not in self._page_to_nodes:
                    self._page_to_nodes[p] = []
                self._page_to_nodes[p].append(node)

        # For pages with multiple nodes, prefer the most specific (smallest range)
        for p in self._page_to_nodes:
            self._page_to_nodes[p].sort(
                key=lambda n: n.get("end_page", 0) - n.get("start_page", 0)
            )


def compute_query_hash(session_id: str, question: str) -> str:
    """Hash for response caching. Normalizes question before hashing."""
    normalized = re.sub(r'\s+', ' ', question.strip().lower())
    return hashlib.md5(f"{session_id}:{normalized}".encode()).hexdigest()
