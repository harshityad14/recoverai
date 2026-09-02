import logging
from typing import Optional
import redis
from app.core.config import settings

logger = logging.getLogger(__name__)

# Redis Client Instance with timeout configuration
redis_client: Optional[redis.Redis] = None

try:
    redis_client = redis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_connect_timeout=1.0,
        socket_timeout=1.0,
    )
except Exception as e:
    logger.warning("Failed to initialize Redis client pool: %s", e)
    redis_client = None


def get_redis() -> Optional[redis.Redis]:
    """Dependency or accessor for obtaining the Redis client instance.

    Returns:
        Optional[redis.Redis]: Redis connection instance.
    """
    return redis_client


def check_redis_connection() -> tuple[bool, str]:
    """Safely verify Redis connectivity.

    Returns:
        tuple[bool, str]: (is_connected, status_message)
    """
    if redis_client is None:
        return False, "disconnected: client not initialized"

    try:
        if redis_client.ping():
            return True, "connected"
        return False, "disconnected: ping returned false"
    except Exception as exc:
        logger.warning("Redis ping check failed: %s", exc)
        return False, f"disconnected: {exc.__class__.__name__}"
