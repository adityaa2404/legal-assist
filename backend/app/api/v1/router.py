from fastapi import APIRouter
from app.api.v1 import documents, analysis, chat, health

api_router = APIRouter()
api_router.include_router(documents.router, tags=["Documents"])
api_router.include_router(analysis.router, tags=["Analysis"])
api_router.include_router(chat.router, tags=["Chat"])
api_router.include_router(health.router, tags=["Health"])
