from pydantic import BaseModel
from typing import Dict, Any, Optional
from datetime import datetime, timezone

class Session(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    pii_mapping: Dict[str, str]
    anonymized_text: Optional[str] = None
    document_metadata: Dict[str, Any]

class SessionCreate(BaseModel):
    pii_mapping: Dict[str, str]
    anonymized_text: Optional[str] = None
    document_metadata: Dict[str, Any]

class SessionUpdate(BaseModel):
    anonymized_text: Optional[str] = None
