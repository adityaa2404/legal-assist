import logging

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


async def _check_worker() -> bool:
    """
    Hit the worker Space's dummy HTTP listener directly.

    HF Spaces sleep independently on free tier and don't wake on traffic to a
    *different* Space — only on a request to their own URL. This same GET
    doubles as the wake ping: if the worker Space is asleep, this request is
    what wakes it, and a later /health poll (frontend polls every 15s) will
    see it come back healthy.
    """
    if not settings.WORKER_URL:
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(settings.WORKER_URL)
            return resp.status_code == 200
    except Exception as exc:
        logger.debug("Worker health check failed (worker may still be waking up): %s", exc)
        return False


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health_check():
    worker_healthy = await _check_worker()
    worker_status = "healthy" if worker_healthy else "starting"
    status = "ok" if worker_healthy else "waking"

    return {
        "status": status,
        "api_status": "ok",
        "worker_status": worker_status,
    }
