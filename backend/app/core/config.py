from pydantic_settings import BaseSettings
from typing import List, Optional
from pydantic import field_validator
import secrets
import json
from urllib.parse import urlparse, parse_qsl, urlencode, urlunparse

class Settings(BaseSettings):
    PROJECT_NAME: str = "legal-assist AI"
    API_V1_STR: str = "/api/v1"

    # MONGODB config
    MONGODB_URI: str
    MONGO_DB_NAME: str = "legal-assist"

    # CLERK config
    CLERK_FRONTEND_API: str = "modest-rattler-9.clerk.accounts.dev"

    # GEMINI config
    GEMINI_API_KEY: str
    GEMINI_HTOC_API_KEY: Optional[str] = None
    GEMINI_CHAT_API_KEY: Optional[str] = None
    GEMINI_MODEL: str = "gemini-3.6-flash"
    GEMINI_TIMEOUT: int = 90
    GROQ_API_KEY: Optional[str] = None
    OPEN_AI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None

    # JWT config
    JWT_SECRET: str = secrets.token_urlsafe(64)

    # SESSION config
    SESSION_SECRET: str = secrets.token_urlsafe(64)
    SESSION_TTL_SECONDS: int = 31536000
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx"]
    MAX_FILE_SIZE_MB: int = 15

    # CORS config
    CORS_ORIGINS: List[str] = ["http://localhost:5173"]

    # REDIS / CELERY config
    REDIS_URL: str
    WORKER_URL: Optional[str] = None

    # RESEND config for visitor wake-request notifications
    RESEND_API_KEY: Optional[str] = None
    RESEND_FROM_EMAIL: str = "onboarding@resend.dev"
    RESEND_TO_EMAIL: Optional[str] = None

    # RATE LIMIT config
    RATE_LIMIT_RPM: int = 300

    # BM25 SEARCH config
    BM25_LOW_THRESHOLD: float = 0.5
    BM25_HIGH_THRESHOLD: float = 2.0

    @field_validator("CORS_ORIGINS", mode="before")
    @classmethod
    def parse_cors_origins(cls, value):
        """Accept JSON array (preferred) and comma-separated values (legacy)."""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            raw = value.strip()
            if not raw:
                return ["http://localhost:5173"]
            if raw.startswith("["):
                return json.loads(raw)
            return [origin.strip() for origin in raw.split(",") if origin.strip()]
        return value

    @field_validator("REDIS_URL", mode="before")
    @classmethod
    def normalize_redis_url(cls, value):
        """Accept a clean Redis URL and recover from a duplicated env key prefix."""
        if isinstance(value, str):
            raw = value.strip().strip('"').strip("'")
            if raw.startswith("REDIS_URL="):
                raw = raw.split("=", 1)[1].strip().strip('"').strip("'")
            if raw and not raw.startswith(("redis://", "rediss://")):
                raise ValueError(
                    "REDIS_URL must start with redis:// or rediss:// (Upstash Redis connection string)"
                )
            if raw.startswith("rediss://"):
                parsed = urlparse(raw)
                query = dict(parse_qsl(parsed.query, keep_blank_values=True))
                if "ssl_cert_reqs" not in query:
                    query["ssl_cert_reqs"] = "required"
                    raw = urlunparse(parsed._replace(query=urlencode(query)))
            return raw
        return value

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
