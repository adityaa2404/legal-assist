from pydantic_settings import BaseSettings
from typing import List, Optional
import secrets

class Settings(BaseSettings):
    PROJECT_NAME: str = "legal-assist AI"
    API_V1_STR: str = "/api/v1"

    # MONGODB config
    MONGODB_URI: str
    MONGO_DB_NAME: str = "legal-assist"

    # GEMINI config
    GEMINI_API_KEY: str           # Used for analysis (primary)
    GEMINI_HTOC_API_KEY: Optional[str] = None  # Separate key for HTOC + tree search
    GEMINI_CHAT_API_KEY: Optional[str] = None  # Separate key for chat
    GEMINI_TIMEOUT: int = 90  # seconds — max wait for any Gemini call

    # JWT config
    JWT_SECRET: str = secrets.token_urlsafe(64)  # Auto-generate if not set

    # SESSION config
    SESSION_SECRET: str = secrets.token_urlsafe(64)
    SESSION_TTL_SECONDS: int = 7200  # 2 hours
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx"]
    MAX_FILE_SIZE_MB: int = 50  # Max upload size (supports up to ~1000 page PDFs)

    # CORS config
    CORS_ORIGINS: List[str] = ["http://localhost", "https://legal-assist.ai", "http://localhost:5173"]

    # OCR is now handled by PaddleOCR (local, no API key needed)

    # SMTP config (optional — for email report feature)
    SMTP_HOST: Optional[str] = None
    SMTP_PORT: int = 587
    SMTP_USER: Optional[str] = None
    SMTP_PASSWORD: Optional[str] = None
    SMTP_FROM_EMAIL: Optional[str] = None
    SMTP_FROM_NAME: str = "Legal Assist AI"

    # RATE LIMIT config
    RATE_LIMIT_RPM: int = 300

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
