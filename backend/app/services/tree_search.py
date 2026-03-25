"""
Tree Search Service for Vectorless RAG.

Uses LLM reasoning to navigate the HTOC tree and find relevant document sections
for a given query. This replaces vector similarity search with structured reasoning.

The LLM examines section summaries in the tree, reasons about which sections are
likely to contain the answer, and returns their node IDs. The actual page text
is then extracted and used as context for answering.
"""

import json
import logging
from typing import List, Dict, Any

logger = logging.getLogger(__name__)

# Maximum context to extract (in characters)
MAX_CONTEXT_CHARS = 50000


class TreeSearchService:
    """
    Searches the HTOC tree using LLM reasoning to find relevant document sections.
    This is the core of vectorless RAG — the LLM reasons about document structure
    instead of relying on vector similarity.
    """

    async def search(
        self,
        tree: Dict[str, Any],
        query: str,
        page_texts: List[str],
        gemini_client,
        max_nodes: int = 5,
    ) -> Dict[str, Any]:
        """
        Search the HTOC tree for sections relevant to a query.

        Args:
            tree: The HTOC tree structure
            query: User's question
            page_texts: List of per-page anonymized text
            gemini_client: GeminiClient instance
            max_nodes: Maximum number of nodes to select

        Returns:
            {
                "context": "extracted relevant text from selected pages",
                "source_sections": [{"title": "...", "pages": "1-3", "node_id": "0001"}],
                "reasoning": "why these sections were selected"
            }
        """
        # Build a lightweight tree (summaries only, no full text)
        tree_structure = self._strip_text(tree)

        prompt = f"""You are a legal document expert. Given a query (which may include prior conversation context) and a document's hierarchical table of contents (HTOC), identify which sections contain the answer.

QUERY:
{query}

DOCUMENT STRUCTURE (HTOC):
{json.dumps(tree_structure, indent=2)}

Return a JSON object:
{{
  "reasoning": "Why these sections are relevant to the query",
  "selected_nodes": ["node_id_1", "node_id_2"],
  "confidence": "high | medium | low"
}}

SELECTION RULES:
1. Precision over breadth: prefer 2-3 highly relevant sections over {max_nodes} weak ones
2. Leaf-first: select the most specific (deepest) section possible
3. Do NOT select a parent if a child node is more specific to the query
4. For broad questions ("summarize", "what is this about"): select the 3-4 most important top-level sections
5. For specific queries (a clause, term, party, amount): find the exact section
6. If the query references prior conversation ("tell me more", "what about that", "their obligations"), use the conversation context to understand what topic is being discussed and select sections for THAT topic
7. Select up to {max_nodes} nodes maximum
- RETURN ONLY VALID JSON"""

        try:
            result = await gemini_client.generate_json(prompt)
            selected_ids = result.get("selected_nodes", [])
            reasoning = result.get("reasoning", "")
            confidence = result.get("confidence", "medium")
        except Exception as e:
            logger.error(f"Tree search failed: {e}, falling back to root sections")
            selected_ids = self._get_top_level_ids(tree)[:max_nodes]
            reasoning = "Fallback: tree search failed, using top-level sections"
            confidence = "low"

        # If low confidence or no results, expand search
        if not selected_ids:
            selected_ids = self._get_top_level_ids(tree)[:max_nodes]
            reasoning = "No nodes selected, using top-level sections"

        # Extract page text from selected nodes
        node_map = self._create_node_map(tree)
        context_parts = []
        source_sections = []
        seen_pages = set()

        for node_id in selected_ids:
            node = node_map.get(node_id)
            if not node:
                continue

            start = node.get("start_page", 0)
            end = node.get("end_page", start)

            # Extract page text for this node
            for page_idx in range(start, min(end + 1, len(page_texts))):
                if page_idx not in seen_pages:
                    seen_pages.add(page_idx)
                    context_parts.append(
                        f"[Page {page_idx + 1} — {node.get('title', 'Section')}]\n{page_texts[page_idx]}"
                    )

            page_range = (
                f"{start + 1}-{end + 1}" if start != end else str(start + 1)
            )
            source_sections.append(
                {
                    "title": node.get("title", f"Section {node_id}"),
                    "pages": page_range,
                    "node_id": node_id,
                }
            )

        context = "\n\n".join(context_parts)

        # Truncate at a sentence boundary if too long
        if len(context) > MAX_CONTEXT_CHARS:
            truncated = context[:MAX_CONTEXT_CHARS]
            # Find the last sentence-ending punctuation to avoid mid-sentence cuts
            last_period = max(truncated.rfind('. '), truncated.rfind('.\n'))
            if last_period > MAX_CONTEXT_CHARS * 0.8:
                truncated = truncated[:last_period + 1]
            context = truncated + "\n\n[Note: Some content was truncated due to length. The above covers the most relevant sections.]"

        return {
            "context": context,
            "source_sections": source_sections,
            "reasoning": reasoning,
        }

    async def search_for_analysis(
        self,
        tree: Dict[str, Any],
        page_texts: List[str],
        gemini_client,
    ) -> str:
        """
        Extract structured context for comprehensive document analysis.
        Unlike search(), this retrieves ALL major sections but organized by the tree.
        This gives the LLM a structured view of the document rather than raw text.

        Returns:
            Structured text with section headers and page references
        """
        return self._build_structured_context(tree, page_texts)

    def _build_structured_context(
        self, node: Dict, page_texts: List[str], depth: int = 0
    ) -> str:
        """Recursively build structured context from the tree."""
        indent = "  " * depth
        parts = []

        title = node.get("title", "Section")
        start = node.get("start_page", 0)
        end = node.get("end_page", start)
        summary = node.get("summary", "")

        # Add section header
        if depth > 0:
            page_ref = f"(Pages {start + 1}-{end + 1})" if start != end else f"(Page {start + 1})"
            parts.append(f"{indent}## {title} {page_ref}")
            if summary:
                parts.append(f"{indent}Summary: {summary}")

        children = node.get("children", [])
        if children:
            # If has children, recurse into them
            for child in children:
                parts.append(
                    self._build_structured_context(child, page_texts, depth + 1)
                )
        else:
            # Leaf node: include actual page text
            for page_idx in range(start, min(end + 1, len(page_texts))):
                parts.append(f"{indent}{page_texts[page_idx]}")

        return "\n".join(parts)

    def _strip_text(self, node: Dict) -> Dict:
        """Create a lightweight copy of the tree (summaries only)."""
        stripped = {
            "title": node.get("title", ""),
            "node_id": node.get("node_id", ""),
            "start_page": node.get("start_page", 0),
            "end_page": node.get("end_page", 0),
            "summary": node.get("summary", ""),
        }
        if node.get("children"):
            stripped["children"] = [
                self._strip_text(c) for c in node["children"]
            ]
        return stripped

    def _create_node_map(self, node: Dict) -> Dict[str, Dict]:
        """Create a flat mapping of node_id -> node for quick lookup."""
        mapping = {}
        node_id = node.get("node_id", "root")
        mapping[node_id] = node
        for child in node.get("children", []):
            mapping.update(self._create_node_map(child))
        return mapping

    def _get_top_level_ids(self, tree: Dict) -> List[str]:
        """Get IDs of top-level children (fallback for failed search)."""
        children = tree.get("children", [])
        if children:
            return [c.get("node_id", "") for c in children if c.get("node_id")]
        return [tree.get("node_id", "root")]

    def _get_all_leaf_ids(self, node: Dict) -> List[str]:
        """Get all leaf node IDs (DFS order)."""
        if not node.get("children"):
            return [node.get("node_id", "")]
        ids = []
        for child in node["children"]:
            ids.extend(self._get_all_leaf_ids(child))
        return ids
