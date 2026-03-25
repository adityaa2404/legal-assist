from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "legal-assist AI"
    API_V1_STR: str = "/api/v1"
    
    # MONGODB config
    MONGODB_URI: str
    MONGO_DB_NAME: str = "legal-assist"
    
    # GEMINI config
    GEMINI_API_KEY: str           # Used for analysis, HTOC, chat
    GEMINI_CHAT_API_KEY: Optional[str] = None  # Separate key for chat (avoids RPM competition)
    
    # JWT config
    JWT_SECRET: str

    # SESSION config
    SESSION_SECRET: str
    SESSION_TTL_SECONDS: int = 7200  # 2 hours
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx"]

    # CORS config
    CORS_ORIGINS: List[str] = ["http://localhost", "https://legal-assist.ai", "http://localhost:5173"]
    
    # OCR is now handled by PaddleOCR (local, no API key needed)

    # RATE LIMIT config
    RATE_LIMIT_RPM: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True
        extra = "ignore"

settings = Settings()
