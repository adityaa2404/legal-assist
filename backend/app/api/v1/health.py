import html
import logging
import time

import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    api_status: str
    worker_status: str


class WakeRequest(BaseModel):
    message: str = Field(min_length=5, max_length=2000)


# How long a worker-status result is trusted before /health re-checks for real.
_WORKER_STATUS_TTL_SECONDS = 300

_worker_status_cache = {"healthy": False, "checked_at": 0.0}
_last_wake_request_at = 0.0
_WAKE_REQUEST_COOLDOWN_SECONDS = 600


async def _check_worker() -> bool:
    """Hit the worker Space's dummy HTTP listener directly."""
    if not settings.WORKER_URL:
        logger.warning("Worker health check skipped: WORKER_URL is not set")
        return False
    try:
        async with httpx.AsyncClient(timeout=5, follow_redirects=True) as client:
            resp = await client.get(settings.WORKER_URL)
            if resp.status_code != 200:
                logger.warning(
                    "Worker health check got non-200: url=%s status=%s body=%r",
                    settings.WORKER_URL,
                    resp.status_code,
                    resp.text[:200],
                )
            return resp.status_code == 200
    except Exception as exc:
        logger.warning("Worker health check failed: url=%s error=%s", settings.WORKER_URL, exc)
        return False


async def get_worker_status(force: bool = False) -> bool:
    """Return worker health, using the cache unless a forced check is requested."""
    now = time.monotonic()
    if not force and (now - _worker_status_cache["checked_at"]) < _WORKER_STATUS_TTL_SECONDS:
        return _worker_status_cache["healthy"]

    healthy = await _check_worker()
    _worker_status_cache["healthy"] = healthy
    _worker_status_cache["checked_at"] = now
    return healthy


def _health_response(worker_healthy: bool) -> dict[str, str]:
    return {
        "status": "ok" if worker_healthy else "waking",
        "api_status": "ok",
        "worker_status": "healthy" if worker_healthy else "starting",
    }


@router.api_route("/health", methods=["GET", "HEAD"], response_model=HealthResponse)
async def health_check():
    return _health_response(await get_worker_status())


@router.post("/health/wake", response_model=HealthResponse)
async def wake_worker():
    """Explicit, caller-intended wake — bypasses the cache unconditionally."""
    return _health_response(await get_worker_status(force=True))


@router.post("/health/request-wake")
async def request_worker_wake(payload: WakeRequest):
    """Email the owner when a visitor cannot wake the worker automatically."""
    global _last_wake_request_at

    if not settings.RESEND_API_KEY or not settings.RESEND_TO_EMAIL:
        logger.error("Wake request email is not configured")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Wake request email is not configured.",
        )

    now = time.monotonic()
    remaining = _WAKE_REQUEST_COOLDOWN_SECONDS - (now - _last_wake_request_at)
    if remaining > 0:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="A wake request was already sent recently. Please try again later.",
        )

    safe_message = html.escape(payload.message.strip())
    email_payload = {
        "from": settings.RESEND_FROM_EMAIL,
        "to": [settings.RESEND_TO_EMAIL],
        "subject": "Legal Assist worker wake request",
        "html": (
            "<h2>Legal Assist worker wake request</h2>"
            "<p>A visitor reported that the analysis worker is unavailable.</p>"
            f"<p><strong>Message:</strong></p><p>{safe_message.replace(chr(10), '<br>')}</p>"
        ),
    }

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(
                "https://api.resend.com/emails",
                headers={
                    "Authorization": f"Bearer {settings.RESEND_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=email_payload,
            )
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("Resend rejected wake request: status=%s body=%s", exc.response.status_code, exc.response.text[:500])
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The wake request could not be sent. Please try again later.",
        ) from exc
    except httpx.HTTPError as exc:
        logger.error("Resend request failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="The wake request could not be sent. Please try again later.",
        ) from exc

    _last_wake_request_at = now
    return {"message": "Your request was sent. We will check the worker shortly."}
