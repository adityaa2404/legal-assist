from app.core.database import get_database
from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class HistoryService:
    def __init__(self):
        db = get_database()
        self.collection = db.analysis_history

    async def save(
        self, user_email: str, analysis: dict, document_metadata: dict,
        page_texts: list = None, htoc_tree: dict = None, pii_mapping: dict = None,
    ):
        """Save analysis + chat data to user's history. No raw document stored."""
        record = {
            "user_email": user_email,
            "created_at": datetime.now(timezone.utc),
            "filename": document_metadata.get("filename", "Unknown"),
            "page_count": document_metadata.get("page_count", 0),
            "document_type": analysis.get("document_type", "Unknown"),
            "summary": analysis.get("summary", ""),
            "overall_risk_score": analysis.get("overall_risk_score", 0),
            "parties": analysis.get("parties", []),
            "key_clauses": analysis.get("key_clauses", []),
            "risks": analysis.get("risks", []),
            "obligations": analysis.get("obligations", []),
            "missing_clauses": analysis.get("missing_clauses", []),
            # Chat data — enables re-chatting with past analyses
            "page_texts": page_texts or [],
            "htoc_tree": htoc_tree,
            "pii_mapping": pii_mapping or {},
        }
        await self.collection.insert_one(record)
        logger.info(f"Saved analysis history for {user_email}: {record['filename']}")

    async def get_user_history(self, user_email: str, limit: int = 20, skip: int = 0) -> list:
        """Get user's analysis history (list view — no heavy fields)."""
        cursor = self.collection.find(
            {"user_email": user_email},
            {
                "_id": 0, "user_email": 0,
                "page_texts": 0, "htoc_tree": 0, "pii_mapping": 0,
            },
        ).sort("created_at", -1).skip(skip).limit(limit)

        return await cursor.to_list(length=limit)

    async def get_full_history_item(self, user_email: str, created_at: str) -> Optional[dict]:
        """Get a single history item with all data (including chat data)."""
        from datetime import datetime as dt
        try:
            ts = dt.fromisoformat(created_at)
        except ValueError:
            return None

        doc = await self.collection.find_one(
            {"user_email": user_email, "created_at": ts},
            {"_id": 0, "user_email": 0},
        )
        return doc
