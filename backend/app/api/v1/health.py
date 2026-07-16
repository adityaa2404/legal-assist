import logging
import time

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    api_status: str
    worker_status: str


# How long a worker-status result is trusted before /health re-checks for real.
# Deliberately long: hitting WORKER_URL is what keeps the worker Space's HF
# Space awake (its own request counts as activity), so checking on every poll
# (frontend polls every 15-30s) never let the worker sleep and kept Celery's
# broker loop running around the clock. The actual wake trigger now lives at
# the upload endpoints (see documents.py) — this cache just gives /health a
# cheap status to report between real checks.
_WORKER_STATUS_TTL_SECONDS = 300

_worker_status_cache = {"healthy": False, "checked_at": 0.0}


async def _check_worker() -> bool:
    """Hit the worker Space's dummy HTTP listener directly (the actual network call)."""
    if not settings.WORKER_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(settings.WORKER_URL)
            return resp.status_code == 200
    except Exception as exc:
        logger.debug("Worker health check failed (worker may still be waking up): %s", exc)
        return False


async def get_worker_status(force: bool = False) -> bool:
    """
    Return whether the worker is healthy, using a cached result unless `force`
    is set or the cache is stale. `force=True` is what actually wakes a
    sleeping worker Space — call it from places where waking the worker is
    genuinely intended (upload endpoints), not from routine status polling.
    """
    now = time.monotonic()
    if not force and (now - _worker_status_cache["checked_at"]) < _WORKER_STATUS_TTL_SECONDS:
        return _worker_status_cache["healthy"]

    healthy = await _check_worker()
    _worker_status_cache["healthy"] = healthy
    _worker_status_cache["checked_at"] = now
    return healthy


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health_check():
    worker_healthy = await get_worker_status()
    worker_status = "healthy" if worker_healthy else "starting"
    status = "ok" if worker_healthy else "waking"

    return {
        "status": status,
        "api_status": "ok",
        "worker_status": worker_status,
    }


@router.post("/health/wake", response_model=HealthResponse)
async def wake_worker():
    """Explicit, caller-intended wake — bypasses the cache unconditionally."""
    worker_healthy = await get_worker_status(force=True)
    worker_status = "healthy" if worker_healthy else "starting"
    status = "ok" if worker_healthy else "waking"

    return {
        "status": status,
        "api_status": "ok",
        "worker_status": worker_status,
    }
