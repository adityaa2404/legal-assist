import asyncio
import logging

import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.core.config import settings
from app.core.redis import is_worker_healthy

logger = logging.getLogger(__name__)

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    api_status: str
    worker_status: str


async def _ping_worker_to_wake_it() -> None:
    """
    Best-effort ping to the worker Space's dummy HTTP listener.

    HF Spaces sleep independently on free tier and don't wake on traffic to a
    *different* Space — only on a request to their own URL. If the API Space
    wakes up but the worker Space is still asleep, uploads queue in Redis with
    nothing consuming them until something happens to hit the worker directly.
    Firing this on every /health call (which the frontend already polls every
    15s) means the worker starts waking the moment a user opens the app,
    instead of only after the first upload silently stalls.
    """
    if not settings.WORKER_URL:
        return
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            await client.get(settings.WORKER_URL)
    except Exception as exc:
        logger.debug("Worker wake ping failed (worker may still be waking up): %s", exc)


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health_check():
    worker_status = "healthy" if is_worker_healthy() else "starting"
    status = "ok" if worker_status == "healthy" else "waking"

    if worker_status != "healthy":
        # Don't block the response on this — the frontend is already polling
        # every 15s and will pick up "healthy" on a later poll once the
        # worker's heartbeat starts landing in Redis.
        asyncio.create_task(_ping_worker_to_wake_it())

    return {
        "status": status,
        "api_status": "ok",
        "worker_status": worker_status,
    }
