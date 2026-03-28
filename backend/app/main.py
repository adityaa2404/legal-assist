from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.database import create_indexes, close_mongo_connection, get_database
from app.api.v1.router import api_router
import os
import uvicorn
import logging

# Clean logging: only show warnings+ from noisy libs, INFO for our code
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-5s  %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
# Silence noisy third-party loggers
for noisy in ("httpx", "httpcore", "google", "urllib3", "motor", "pymongo", "presidio", "fontTools", "weasyprint"):
    logging.getLogger(noisy).setLevel(logging.WARNING)

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)


async def _recover_stuck_sessions():
    """Mark sessions stuck in 'processing' for >30 minutes as 'failed'."""
    try:
        from datetime import datetime, timedelta, timezone
        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = await db.sessions.update_many(
            {"htoc_status": "processing", "created_at": {"$lt": cutoff}},
            {"$set": {"htoc_status": "failed"}},
        )
        if result.modified_count:
            logger.warning("Recovered %d stuck sessions (processing > 30 min)", result.modified_count)
    except Exception as e:
        logger.error("Failed to recover stuck sessions: %s", e)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: create indexes, verify Atlas connection
    await create_indexes()

    # Warn about auto-generated secrets
    if not os.environ.get("JWT_SECRET"):
        logger.warning("JWT_SECRET not set in .env — auto-generated. All user tokens will invalidate on restart!")
    if not os.environ.get("SESSION_SECRET"):
        logger.warning("SESSION_SECRET not set in .env — auto-generated. Sessions will break on restart!")

    # Warn about dev CORS origins in production
    dev_origins = [o for o in settings.CORS_ORIGINS if "localhost" in o]
    if dev_origins and any("https://" in o for o in settings.CORS_ORIGINS):
        logger.warning("CORS allows localhost origins alongside production domains: %s", dev_origins)

    # Clean up stuck sessions from previous crashes
    await _recover_stuck_sessions()

    yield
    # Shutdown: close MongoDB connection
    await close_mongo_connection()


app = FastAPI(
    title=settings.PROJECT_NAME,
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    lifespan=lifespan,
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID"],
)

# Set up Rate Limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Include API router
app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/")
async def root():
    return {"message": "Welcome to legal-assist AI API"}

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
