from pydantic import BaseModel
from typing import List, Optional, Dict


class ChatMessage(BaseModel):
    role: str
    content: str


class SourceSection(BaseModel):
    title: str
    pages: str
    node_id: str


class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage]


class ChatResponse(BaseModel):
    response: str
    source_sections: Optional[List[SourceSection]] = None
