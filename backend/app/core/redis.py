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


def is_worker_healthy() -> bool:
    """Check whether the worker's heartbeat key is present and fresh (single Redis read)."""
    try:
        value = get_redis_client().get(WORKER_HEARTBEAT_KEY)
        if not value:
            return False

        from time import time

        age = time() - float(value)
        return 0 <= age <= WORKER_HEARTBEAT_STALE_SECONDS
    except Exception as exc:
        logger.warning("Unable to read worker heartbeat: %s", exc)
        return False
