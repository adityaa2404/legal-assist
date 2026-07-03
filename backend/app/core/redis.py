import logging

import redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None

WORKER_HEARTBEAT_KEY = "worker:heartbeat"
WORKER_HEARTBEAT_TTL_SECONDS = 45
WORKER_HEARTBEAT_STALE_SECONDS = 45


def get_redis_client() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=3,
            socket_connect_timeout=3,
            health_check_interval=30,
        )
    return _client


def get_worker_heartbeat_age_seconds() -> float | None:
    """Return the worker heartbeat age in seconds, or None if unavailable."""
    try:
        value = get_redis_client().get(WORKER_HEARTBEAT_KEY)
        if not value:
            return None

        heartbeat_ts = float(value)
        from time import time

        return max(0.0, time() - heartbeat_ts)
    except Exception as exc:
        logger.warning("Unable to read worker heartbeat: %s", exc)
        return None


def is_worker_healthy() -> bool:
    age = get_worker_heartbeat_age_seconds()
    return age is not None and age <= WORKER_HEARTBEAT_STALE_SECONDS
