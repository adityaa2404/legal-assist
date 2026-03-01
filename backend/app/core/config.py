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
    
    # PINECONE config
    PINECONE_API_KEY: str
    PINECONE_INDEX_NAME: str = "rulebook"
    
    # SESSION config
    SESSION_SECRET: str
    SESSION_TTL_SECONDS: int = 7200  # 2 hours
    
    # FILE UPLOAD config
    MAX_FILE_SIZE_MB: int = 20
    ALLOWED_EXTENSIONS: List[str] = ["pdf", "docx"]
    
    # CORS config
    CORS_ORIGINS: List[str] = ["http://localhost", "https://legal-assist.ai", "http://localhost:5173"]
    
    # RATE LIMIT config
    RATE_LIMIT_RPM: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True

settings = Settings()
