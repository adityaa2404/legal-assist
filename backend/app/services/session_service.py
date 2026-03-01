from motor.motor_asyncio import AsyncIOMotorClient
from app.core.config import settings
from app.models.session import Session, SessionCreate, SessionUpdate
from typing import Optional
from datetime import datetime, timedelta, timezone
from bson import ObjectId
import uuid

class SessionService:
    def __init__(self):
        self.client = AsyncIOMotorClient(settings.MONGODB_URI)
        self.db = self.client[settings.MONGO_DB_NAME]
        self.collection = self.db.sessions

    async def create(self, pii_mapping: dict, anonymized_text: str, document_metadata: dict) -> Session:
        session_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(seconds=settings.SESSION_TTL_SECONDS)
        
        session_data = {
            "session_id": session_id,
            "created_at": now,
            "expires_at": expires_at,
            "pii_mapping": pii_mapping,
            "anonymized_text": anonymized_text,
            "document_metadata": document_metadata
        }
        
        await self.collection.insert_one(session_data)
        return Session(**session_data)

    async def get(self, session_id: str) -> Optional[Session]:
        result = await self.collection.find_one({"session_id": session_id})
        if result:
            return Session(**result)
        return None

    async def update(self, session_id: str, update_data: SessionUpdate) -> Optional[Session]:
        update_dict = update_data.dict(exclude_unset=True)
        if not update_dict:
            return await self.get(session_id)
            
        await self.collection.update_one(
            {"session_id": session_id},
            {"$set": update_dict}
        )
        return await self.get(session_id)

    async def delete(self, session_id: str):
        await self.collection.delete_one({"session_id": session_id})
