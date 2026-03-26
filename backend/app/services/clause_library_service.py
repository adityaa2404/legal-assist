"""Service for managing user's saved clause library across documents."""

from app.core.database import get_database
from datetime import datetime, timezone
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class ClauseLibraryService:
    def __init__(self):
        db = get_database()
        self.collection = db.clause_library

    async def save_clause(self, user_email: str, clause: dict, source_filename: str) -> str:
        """Save a clause to the user's library. Returns the inserted ID."""
        record = {
            "user_email": user_email,
            "created_at": datetime.now(timezone.utc),
            "source_filename": source_filename,
            "clause_title": clause.get("clause_title", ""),
            "clause_text": clause.get("clause_text", ""),
            "plain_english": clause.get("plain_english", ""),
            "importance": clause.get("importance", "standard"),
            "notes": clause.get("notes", ""),
        }
        result = await self.collection.insert_one(record)
        logger.info("Saved clause '%s' for %s", record["clause_title"], user_email)
        return str(result.inserted_id)

    async def get_library(self, user_email: str, limit: int = 50, skip: int = 0) -> list:
        """Get all saved clauses for a user."""
        cursor = self.collection.find(
            {"user_email": user_email},
            {"_id": 0, "user_email": 0},
        ).sort("created_at", -1).skip(skip).limit(limit)
        return await cursor.to_list(length=limit)

    async def count(self, user_email: str) -> int:
        return await self.collection.count_documents({"user_email": user_email})

    async def delete_clause(self, user_email: str, clause_title: str, created_at: str) -> bool:
        """Delete a specific clause from the library."""
        from datetime import datetime as dt
        try:
            ts = dt.fromisoformat(created_at)
        except ValueError:
            return False

        result = await self.collection.delete_one({
            "user_email": user_email,
            "clause_title": clause_title,
            "created_at": ts,
        })
        return result.deleted_count > 0
