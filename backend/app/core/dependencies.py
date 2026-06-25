import logging
import httpx
from jose import jwt as pyjwt, JWTError
from jose.backends import RSAKey
import json

from app.services.pii_anonymizer import PIIAnonymizer
from app.services.document_parser import DocumentParser
from app.services.session_service import SessionService
from app.services.gemini_client import GeminiClient
from app.services.htoc_builder import HTOCBuilder
from app.services.tree_search import TreeSearchService
from app.services.bm25_search import BM25SearchService

from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer()

# Singleton — GeminiClient has no mutable state, underlying API clients are module-level
_gemini_instance: GeminiClient = None


def get_gemini_client() -> GeminiClient:
    global _gemini_instance
    if _gemini_instance is None:
        _gemini_instance = GeminiClient()
    return _gemini_instance

def get_pii_service() -> PIIAnonymizer:
    return PIIAnonymizer()

def get_parser() -> DocumentParser:
    return DocumentParser()

def get_session_service() -> SessionService:
    return SessionService()

def get_htoc_builder() -> HTOCBuilder:
    return HTOCBuilder()

def get_tree_search() -> TreeSearchService:
    return TreeSearchService()

def get_bm25_search() -> BM25SearchService:
    return BM25SearchService()


# ── Clerk JWT verification ──────────────────────────────────────────────────

# JWKS is fetched once and cached in-process. Clerk rotates keys rarely;
# on verification failure we re-fetch once to handle key rotation.
_jwks_cache: dict | None = None

async def _get_jwks() -> dict:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache
    from app.core.config import settings
    jwks_url = f"https://{settings.CLERK_FRONTEND_API}/.well-known/jwks.json"
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.get(jwks_url)
        resp.raise_for_status()
        _jwks_cache = resp.json()
    return _jwks_cache


async def _verify_clerk_token(token: str) -> str:
    """Verify a Clerk-issued JWT and return the user's email (or user_id as fallback)."""
    global _jwks_cache
    for attempt in range(2):
        try:
            jwks = await _get_jwks()

            # Extract kid from unverified header using python-jose
            unverified = pyjwt.get_unverified_header(token)
            kid = unverified.get("kid")

            # Find matching key in JWKS
            key_data = next((k for k in jwks.get("keys", []) if k.get("kid") == kid), None)
            if not key_data:
                raise ValueError(f"No matching JWKS key for kid={kid}")

            # Build RSA public key from JWK using python-jose
            public_key = RSAKey(key_data, algorithm="RS256")

            payload = pyjwt.decode(
                token,
                public_key,
                algorithms=["RS256"],
                options={"verify_aud": False},
            )

            email = payload.get("email") or payload.get("sub", "")
            if not email:
                raise ValueError("Token has no email or sub claim")
            return email

        except Exception as e:
            if attempt == 0:
                _jwks_cache = None
                logger.warning("Clerk token verification failed (attempt 1), retrying: %s", e)
            else:
                logger.error("Clerk token verification failed: %s", e)
                raise


def _verify_local_token(token: str) -> str | None:
    """Try to verify a locally-issued HS256 JWT. Returns email or None if not a local token."""
    from app.core.config import settings
    from jose import jwt as jose_jwt, JWTError
    try:
        payload = jose_jwt.decode(token, settings.JWT_SECRET, algorithms=["HS256"])
        return payload.get("sub")
    except JWTError:
        return None


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
) -> str:
    """Accept either a locally-issued HS256 JWT or a Clerk RS256 JWT."""
    token = credentials.credentials

    # Try local JWT first (fast, no network)
    email = _verify_local_token(token)
    if email:
        return email

    # Fall back to Clerk verification
    try:
        return await _verify_clerk_token(token)
    except Exception:
        raise HTTPException(401, "Invalid or expired token")
