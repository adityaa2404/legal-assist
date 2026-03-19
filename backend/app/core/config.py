from pydantic_settings import BaseSettings
from typing import List, Optional

class Settings(BaseSettings):
    PROJECT_NAME: str = "legal-assist AI"
    API_V1_STR: str = "/api/v1"
    
    # MONGODB config
    MONGODB_URI: str
    MONGO_DB_NAME: str = "legal-assist"
    
    # GEMINI config
    GEMINI_API_KEY: str
    
    # JWT config
    JWT_SECRET: str

    # SESSION config
    SESSION_SECRET: str
    SESSION_TTL_SECONDS: int = 7200  # 2 hours
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx"]

    # CORS config
    CORS_ORIGINS: List[str] = ["http://localhost", "https://legal-assist.ai", "http://localhost:5173"]
    
    # SARVAM AI config (multilingual OCR for scanned documents)
    SARVAM_AI_API_KEY: Optional[str] = None

    # RATE LIMIT config
    RATE_LIMIT_RPM: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
