from pydantic import BaseModel
from typing import Dict, Any, Optional, List
from datetime import datetime, timezone

class Session(BaseModel):
    session_id: str
    created_at: datetime
    expires_at: datetime
    pii_mapping: Dict[str, str]
    anonymized_text: Optional[str] = None
    page_texts: Optional[List[str]] = None  # Per-page anonymized text for HTOC
    htoc_tree: Optional[Dict[str, Any]] = None  # Hierarchical Table of Contents
    bm25_data: Optional[Dict[str, Any]] = None  # Serialized BM25 index data
    htoc_status: Optional[str] = "pending"  # pending | building | ready | failed
    document_metadata: Dict[str, Any]

class SessionCreate(BaseModel):
    pii_mapping: Dict[str, str]
    anonymized_text: Optional[str] = None
    page_texts: Optional[List[str]] = None
    htoc_tree: Optional[Dict[str, Any]] = None
    bm25_data: Optional[Dict[str, Any]] = None
    htoc_status: Optional[str] = "pending"
    document_metadata: Dict[str, Any]

class SessionUpdate(BaseModel):
    anonymized_text: Optional[str] = None
    page_texts: Optional[List[str]] = None
    htoc_tree: Optional[Dict[str, Any]] = None
    bm25_data: Optional[Dict[str, Any]] = None
    htoc_status: Optional[str] = None
