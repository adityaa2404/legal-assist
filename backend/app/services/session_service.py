from app.core.database import get_database
from app.models.session import Session, SessionCreate, SessionUpdate
from typing import Optional
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from pymongo.errors import PyMongoError
import logging
import uuid

logger = logging.getLogger(__name__)

class SessionService:
    def __init__(self):
        db = get_database()
        self.collection = db.sessions

    async def create(
        self,
        pii_mapping: dict,
        anonymized_text: str,
        document_metadata: dict,
        page_texts: list = None,
        htoc_tree: dict = None,
        bm25_data: dict = None,
        htoc_status: str = "pending",
        user_email: str = None,
    ) -> Session:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.SESSION_TTL_SECONDS)

        session_data = {
            "session_id": session_id,
            "user_email": user_email,
            "created_at": now,
            "expires_at": expires_at,
            "pii_mapping": pii_mapping,
            "anonymized_text": anonymized_text,
            "page_texts": page_texts,
            "htoc_tree": htoc_tree,
            "bm25_data": bm25_data,
            "htoc_status": htoc_status,
            "document_metadata": document_metadata,
        }

        await self.collection.insert_one(session_data)
        return Session(**session_data)

    async def get(self, session_id: str) -> Optional[Session]:
        try:
            result = await self.collection.find_one({"session_id": session_id})
        except PyMongoError as e:
            logger.error("MongoDB read failed for session %s: %s", session_id, e)
            return None
        if result:
            return Session(**result)
        return None

    async def get_for_user(self, session_id: str, user_email: str) -> Optional[Session]:
        """Get session only if it belongs to the given user."""
        session = await self.get(session_id)
        if not session:
            return None
        if session.user_email and session.user_email != user_email:
            return None  # Belongs to a different user
        return session

    async def update(self, session_id: str, update_data: SessionUpdate) -> Optional[Session]:
        update_dict = update_data.dict(exclude_unset=True)
        if not update_dict:
            return await self.get(session_id)
            
        await self.collection.update_one(
            {"session_id": session_id},
            {"$set": update_dict}
        )
        return await self.get(session_id)

    async def save_analysis(self, session_id: str, analysis_type: str, result: dict):
        """Cache analysis result in the session to avoid re-running Gemini."""
        field = f"cached_analysis_{analysis_type}"
        await self.collection.update_one(
            {"session_id": session_id},
            {"$set": {field: result}}
        )

    async def get_analysis(self, session_id: str, analysis_type: str) -> Optional[dict]:
        """Retrieve cached analysis result."""
        field = f"cached_analysis_{analysis_type}"
        doc = await self.collection.find_one(
            {"session_id": session_id},
            {field: 1}
        )
        if doc:
            return doc.get(field)
        return None

    async def update_htoc_and_bm25(
        self, session_id: str, htoc_tree: dict, bm25_data: dict, status: str = "ready"
    ):
        """Update session with completed HTOC tree + BM25 index data."""
        await self.collection.update_one(
            {"session_id": session_id},
            {"$set": {
                "htoc_tree": htoc_tree,
                "bm25_data": bm25_data,
                "htoc_status": status,
            }}
        )

    async def set_htoc_status(self, session_id: str, status: str):
        """Update HTOC build status (pending/building/ready/failed)."""
        await self.collection.update_one(
            {"session_id": session_id},
            {"$set": {"htoc_status": status}}
        )

    async def cache_chat_response(self, session_id: str, query_hash: str, response: str, source_sections: list):
        """Cache a chat response for repeated questions."""
        await self.collection.update_one(
            {"session_id": session_id},
            {"$set": {f"chat_cache.{query_hash}": {
                "response": response,
                "source_sections": source_sections,
            }}}
        )

    async def get_cached_chat(self, session_id: str, query_hash: str) -> dict:
        """Retrieve a cached chat response."""
        doc = await self.collection.find_one(
            {"session_id": session_id},
            {f"chat_cache.{query_hash}": 1}
        )
        if doc and doc.get("chat_cache"):
            return doc["chat_cache"].get(query_hash)
        return None

    async def delete(self, session_id: str):
        await self.collection.delete_one({"session_id": session_id})
