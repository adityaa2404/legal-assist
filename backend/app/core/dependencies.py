from app.services.pii_anonymizer import PIIAnonymizer
from app.services.document_parser import DocumentParser
from app.services.session_service import SessionService
from app.services.gemini_client import GeminiClient
from app.services.auth_service import AuthService
from app.services.htoc_builder import HTOCBuilder
from app.services.tree_search import TreeSearchService
from app.services.bm25_search import BM25SearchService

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

_bearer_scheme = HTTPBearer()


def get_gemini_client() -> GeminiClient:
    return GeminiClient()

def get_pii_service(gemini: GeminiClient = Depends(get_gemini_client)) -> PIIAnonymizer:
    return PIIAnonymizer(gemini_client=gemini)

def get_parser() -> DocumentParser:
    return DocumentParser()

def get_session_service() -> SessionService:
    return SessionService()

def get_auth_service() -> AuthService:
    return AuthService()

def get_htoc_builder() -> HTOCBuilder:
    return HTOCBuilder()

def get_tree_search() -> TreeSearchService:
    return TreeSearchService()

def get_bm25_search() -> BM25SearchService:
    return BM25SearchService()

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    auth_service: AuthService = Depends(get_auth_service),
) -> str:
    """Extract and validate JWT from Authorization: Bearer <token>. Returns user email."""
    email = auth_service.decode_token(credentials.credentials)
    if not email:
        raise HTTPException(401, "Invalid or expired token")
    user = await auth_service.get_user_by_email(email)
    if not user or not user.is_active:
        raise HTTPException(401, "User not found or inactive")
    return email
