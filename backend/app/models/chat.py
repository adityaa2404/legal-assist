from pydantic import BaseModel
from typing import List, Optional, Dict


class ChatMessage(BaseModel):
    role: str
    content: str


class SourceSection(BaseModel):
    title: str
    pages: str        # display string e.g. "1-3" or "5"
    page_start: int   # 1-indexed, for PDF viewer navigation
    page_end: int     # 1-indexed, inclusive
    node_id: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]


class ChatResponse(BaseModel):
    response: str
    source_sections: Optional[List[SourceSection]] = None
    retrieval_confidence: Optional[str] = None  # "high" | "medium" | "low"
