from app.services.pii_anonymizer import PIIAnonymizer
from app.services.document_parser import DocumentParser
from app.services.session_service import SessionService
from app.services.gemini_client import GeminiClient
from app.services.pinecone_service import PineconeService

from fastapi import Depends

def get_gemini_client() -> GeminiClient:
    return GeminiClient()

def get_pii_service(gemini: GeminiClient = Depends(get_gemini_client)) -> PIIAnonymizer:
    return PIIAnonymizer(gemini_client=gemini)

def get_parser() -> DocumentParser:
    return DocumentParser()

def get_session_service() -> SessionService:
    return SessionService()

def get_pinecone_service() -> PineconeService:
    return PineconeService()
