"""
HTOC (Hierarchical Table of Contents) Builder Service.

Implements vectorless RAG by building a hierarchical tree index of document structure
using LLM reasoning, inspired by PageIndex (https://github.com/VectifyAI/PageIndex).

Instead of vector embeddings, the document is organized into a navigable tree that
an LLM can reason over to find relevant sections for any query.
"""

import asyncio
import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Max pages to include in a single HTOC building prompt
MAX_PAGES_PER_PROMPT = 100
# Max chars per page preview in the prompt
MAX_CHARS_PER_PAGE_PREVIEW = 600
# Skip HTOC for very small docs (BM25 alone is good enough)
SKIP_HTOC_THRESHOLD = 3


class HTOCBuilder:
    """
    Builds a Hierarchical Table of Contents (HTOC) from document pages.
    Uses LLM reasoning to understand document structure without vector embeddings.
    """

    async def build_tree(self, page_texts: List[str], gemini_client) -> Dict[str, Any]:
        """
        Build an HTOC tree from anonymized page texts.

        Args:
            page_texts: List of text content per page (anonymized)
            gemini_client: GeminiClient instance for LLM calls

        Returns:
            HTOC tree as a dictionary
        """
        if not page_texts:
            return self._empty_tree()

        num_pages = len(page_texts)

        # For very small docs (≤3 pages), skip the LLM call entirely.
        # BM25 keyword search is sufficient — saves 1 Gemini call.
        if num_pages <= SKIP_HTOC_THRESHOLD:
            logger.info(f"Small doc ({num_pages} pages), using simple tree (no LLM call)")
            return self._simple_tree(page_texts)

        if num_pages <= MAX_PAGES_PER_PROMPT:
            return await self._build_tree_single(page_texts, gemini_client)
        else:
            return await self._build_tree_chunked(page_texts, gemini_client)

    async def _build_tree_single(
        self, page_texts: List[str], gemini_client
    ) -> Dict[str, Any]:
        """Build tree from all pages in a single LLM call."""
        page_previews = self._create_page_previews(page_texts)

        prompt = f"""You are a legal document structure analyzer. Analyze the following document pages and build a hierarchical table of contents (HTOC) that captures the document's logical structure.

DOCUMENT PAGES:
{page_previews}

Return a JSON object with this exact structure:
{{
  "title": "Document title or type (e.g., 'Lease Agreement between [PERSON_1] and [PERSON_2]')",
  "node_id": "root",
  "start_page": 0,
  "end_page": {len(page_texts) - 1},
  "summary": "Brief overall document summary (2-3 sentences)",
  "children": [
    {{
      "title": "Section/Clause name (e.g., 'Definitions', 'Term and Termination')",
      "node_id": "0001",
      "start_page": 0,
      "end_page": 2,
      "summary": "What this section covers (1-2 sentences)",
      "children": [
        {{
          "title": "Sub-section name",
          "node_id": "0002",
          "start_page": 0,
          "end_page": 1,
          "summary": "Sub-section content description",
          "children": []
        }}
      ]
    }}
  ]
}}

RULES:
- Every page must be covered by at least one node
- node_id must be unique 4-digit strings (0001, 0002, 0003, etc.)
- start_page and end_page are 0-indexed and inclusive
- Identify natural document sections: preamble/recitals, definitions, individual clauses/articles, schedules/annexures, signature blocks
- Create children for sub-sections when the document has nested structure
- Keep summaries concise but informative — they will be used for retrieval
- For legal documents, capture clause numbers and names precisely
- Preserve anonymized placeholders like [PERSON_1] as-is
- RETURN ONLY VALID JSON, no markdown formatting"""

        try:
            tree = await gemini_client.generate_json(prompt)
            return self._validate_tree(tree, len(page_texts))
        except Exception as e:
            logger.error(f"HTOC building failed: {e}")
            return self._fallback_tree(page_texts)

    async def _build_tree_chunked(
        self, page_texts: List[str], gemini_client
    ) -> Dict[str, Any]:
        """Build tree for large documents by processing chunks with controlled concurrency."""
        chunk_size = MAX_PAGES_PER_PROMPT

        # Limit concurrent Gemini calls to avoid rate limits
        # Free tier: 5 req/min → allow 2 concurrent to leave room for other calls
        semaphore = asyncio.Semaphore(2)

        async def _build_chunk(start: int) -> Dict[str, Any]:
            async with semaphore:
                end = min(start + chunk_size, len(page_texts))
                chunk = page_texts[start:end]
                sub_tree = await self._build_tree_single(chunk, gemini_client)
                self._offset_pages(sub_tree, start)
                return sub_tree

        tasks = [_build_chunk(s) for s in range(0, len(page_texts), chunk_size)]
        sub_trees = await asyncio.gather(*tasks, return_exceptions=True)

        # Handle any failed chunks with fallback trees
        resolved = []
        for i, result in enumerate(sub_trees):
            if isinstance(result, Exception):
                start = i * chunk_size
                end = min(start + chunk_size, len(page_texts))
                logger.warning(f"Chunk {i} failed: {result}, using fallback")
                fallback = self._fallback_tree_from_count(end - start)
                self._offset_pages(fallback, start)
                resolved.append(fallback)
            else:
                resolved.append(result)
        sub_trees = resolved

        if len(sub_trees) == 1:
            return sub_trees[0]

        # Merge sub-trees: ask LLM to create a unified structure
        merge_prompt = self._build_merge_prompt(sub_trees, len(page_texts))
        try:
            merged = await gemini_client.generate_json(merge_prompt)
            return self._validate_tree(merged, len(page_texts))
        except Exception as e:
            logger.warning(f"Tree merge failed, using flat merge: {e}")
            # Flat merge fallback
            all_children = []
            for st in sub_trees:
                children = st.get("children", [])
                if children:
                    all_children.extend(children)
                else:
                    all_children.append(st)

            return {
                "title": sub_trees[0].get("title", "Document"),
                "node_id": "root",
                "start_page": 0,
                "end_page": len(page_texts) - 1,
                "summary": sub_trees[0].get("summary", ""),
                "children": all_children,
            }

    def _build_merge_prompt(
        self, sub_trees: List[Dict], total_pages: int
    ) -> str:
        """Build a prompt to merge multiple sub-trees into one coherent HTOC."""
        trees_json = json.dumps(
            [self._strip_for_merge(st) for st in sub_trees], indent=2
        )
        return f"""You are merging multiple partial table-of-contents trees into one unified hierarchical structure for a legal document spanning {total_pages} pages.

PARTIAL TREES:
{trees_json}

Merge these into a single coherent HTOC tree. Combine sections that span across chunk boundaries. Return a JSON object with the same structure:
{{
  "title": "Document title",
  "node_id": "root",
  "start_page": 0,
  "end_page": {total_pages - 1},
  "summary": "Overall document summary",
  "children": [...]
}}

RULES:
- Merge sections that were split across chunks
- Maintain unique 4-digit node_ids
- Keep page references accurate
- RETURN ONLY VALID JSON"""

    def _strip_for_merge(self, tree: Dict) -> Dict:
        """Strip a tree to essential fields for merging."""
        result = {
            "title": tree.get("title", ""),
            "node_id": tree.get("node_id", ""),
            "start_page": tree.get("start_page", 0),
            "end_page": tree.get("end_page", 0),
            "summary": tree.get("summary", ""),
        }
        if tree.get("children"):
            result["children"] = [
                self._strip_for_merge(c) for c in tree["children"]
            ]
        return result

    def _create_page_previews(self, page_texts: List[str]) -> str:
        """Create truncated page previews for the prompt."""
        previews = []
        for i, text in enumerate(page_texts):
            preview = text[:MAX_CHARS_PER_PAGE_PREVIEW].strip()
            if len(text) > MAX_CHARS_PER_PAGE_PREVIEW:
                preview += "..."
            previews.append(f"--- Page {i} ---\n{preview}")
        return "\n\n".join(previews)

    def _validate_tree(self, tree: Dict, num_pages: int) -> Dict:
        """Validate and fix the HTOC tree structure."""
        if not isinstance(tree, dict):
            return self._fallback_tree_from_count(num_pages)

        tree.setdefault("title", "Document")
        tree.setdefault("node_id", "root")
        tree.setdefault("start_page", 0)
        tree.setdefault("end_page", num_pages - 1)
        tree.setdefault("summary", "")
        tree.setdefault("children", [])

        # Ensure all children have required fields
        self._fix_children(tree)
        return tree

    def _fix_children(self, node: Dict):
        """Recursively ensure all nodes have required fields."""
        for i, child in enumerate(node.get("children", [])):
            child.setdefault("title", f"Section {i + 1}")
            child.setdefault("node_id", f"{i + 1:04d}")
            child.setdefault("start_page", node.get("start_page", 0))
            child.setdefault("end_page", node.get("end_page", 0))
            child.setdefault("summary", "")
            child.setdefault("children", [])
            self._fix_children(child)

    def _offset_pages(self, node: Dict, offset: int):
        """Offset page numbers in a tree node and its children."""
        node["start_page"] = node.get("start_page", 0) + offset
        node["end_page"] = node.get("end_page", 0) + offset
        for child in node.get("children", []):
            self._offset_pages(child, offset)

    def _fallback_tree(self, page_texts: List[str]) -> Dict:
        """Create a simple fallback tree when LLM fails."""
        return self._fallback_tree_from_count(len(page_texts))

    def _fallback_tree_from_count(self, num_pages: int) -> Dict:
        """Create a flat tree with one node per page."""
        children = []
        for i in range(num_pages):
            children.append(
                {
                    "title": f"Page {i + 1}",
                    "node_id": f"{i + 1:04d}",
                    "start_page": i,
                    "end_page": i,
                    "summary": f"Content on page {i + 1}",
                    "children": [],
                }
            )
        return {
            "title": "Document",
            "node_id": "root",
            "start_page": 0,
            "end_page": num_pages - 1,
            "summary": "Document content",
            "children": children,
        }

    def _simple_tree(self, page_texts: List[str]) -> Dict:
        """Build a lightweight tree for small docs without an LLM call."""
        children = []
        for i, text in enumerate(page_texts):
            # Use first 80 chars as a title hint
            first_line = text.strip().split("\n")[0][:80] if text.strip() else f"Page {i+1}"
            children.append({
                "title": first_line,
                "node_id": f"{i+1:04d}",
                "start_page": i,
                "end_page": i,
                "summary": text[:200].strip() if text else "",
                "children": [],
            })
        return {
            "title": children[0]["title"] if children else "Document",
            "node_id": "root",
            "start_page": 0,
            "end_page": len(page_texts) - 1,
            "summary": "Small document — indexed by page",
            "children": children,
        }

    def _empty_tree(self) -> Dict:
        return {
            "title": "Empty Document",
            "node_id": "root",
            "start_page": 0,
            "end_page": 0,
            "summary": "No content",
            "children": [],
        }
