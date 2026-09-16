from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from contextlib import asynccontextmanager
from app.core.config import settings
from app.core.database import create_indexes, close_mongo_connection, get_database
from app.api.v1.router import api_router
from app.core.observability import configure_logging, log_event, new_request_id, request_id_ctx, session_id_ctx
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from prometheus_fastapi_instrumentator import Instrumentator
from starlette.responses import Response
import os
import time
import uvicorn
import logging

configure_logging()
logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)

async def _recover_stuck_sessions():
    try:
        from datetime import datetime, timedelta, timezone
        db = get_database()
        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        result = await db.sessions.update_many(
            {"htoc_status": "processing", "created_at": {"$lt": cutoff}},
            {"$set": {"htoc_status": "failed"}},
        )
        if result.modified_count:
            log_event(logger, logging.WARNING, "stuck_sessions_recovered", recovered=result.modified_count)
    except Exception:
        logger.exception("Failed to recover stuck sessions")

@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_indexes()
    if not os.environ.get("JWT_SECRET"):
        log_event(logger, logging.WARNING, "missing_secret_configuration", secret="JWT_SECRET")
    if not os.environ.get("SESSION_SECRET"):
        log_event(logger, logging.WARNING, "missing_secret_configuration", secret="SESSION_SECRET")
    await _recover_stuck_sessions()
    log_event(logger, logging.INFO, "application_started")
    yield
    await close_mongo_connection()
    log_event(logger, logging.INFO, "application_stopped")

app = FastAPI(title=settings.PROJECT_NAME, openapi_url=f"{settings.API_V1_STR}/openapi.json", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Session-ID", "X-Request-ID"],
)

@app.middleware("http")
async def observability_middleware(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or new_request_id()
    session_id = request.headers.get("X-Session-ID")
    request_token = request_id_ctx.set(request_id)
    session_token = session_id_ctx.set(session_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = round((time.perf_counter() - started) * 1000, 2)
        response.headers["X-Request-ID"] = request_id
        log_event(logger, logging.INFO, "http_request_completed", method=request.method, path=request.url.path, status_code=response.status_code, duration_ms=duration_ms)
        return response
    except Exception:
        log_event(logger, logging.ERROR, "http_request_failed", method=request.method, path=request.url.path)
        logger.exception("Unhandled request exception")
        raise
    finally:
        request_id_ctx.reset(request_token)
        session_id_ctx.reset(session_token)

@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.include_router(api_router, prefix=settings.API_V1_STR)
Instrumentator().instrument(app).expose(app, endpoint="/metrics", include_in_schema=False)

@app.get("/")
async def root():
    return {"message": "Welcome to legal-assist AI API"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
