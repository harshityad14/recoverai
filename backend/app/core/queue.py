"""Redis queue operations for webhook event processing.

Provides an abstraction over Redis list-based queues used for enqueuing
verified webhook events for downstream processing.
"""

import json
import logging
from typing import Any, Dict, Optional, Protocol

logger = logging.getLogger(__name__)

# Default queue name for verified Razorpay webhook events
WEBHOOK_QUEUE_NAME = "recoverai:webhooks"

# Redis key prefix for idempotency tracking
IDEMPOTENCY_KEY_PREFIX = "recoverai:event_id:"

# Idempotency window in seconds (24 hours)
IDEMPOTENCY_TTL_SECONDS = 86400


class RedisQueueClient(Protocol):
    """Protocol defining the minimal Redis interface needed for queue operations.

    This allows both real Redis clients and mock/fake implementations
    for testing without requiring a running Redis server.
    """

    def lpush(self, name: str, *values: Any) -> int: ...
    def rpop(self, name: str) -> Optional[str]: ...
    def get(self, name: str) -> Optional[str]: ...
    def set(self, name: str, value: Any, ex: Optional[int] = None) -> bool: ...
    def llen(self, name: str) -> int: ...
    def lrange(self, name: str, start: int, end: int) -> list: ...


def is_duplicate_event(
    redis_client: RedisQueueClient,
    event_id: str,
) -> bool:
    """Check if a webhook event has already been processed.

    Uses the X-Razorpay-Event-Id header value as the idempotency key.

    Args:
        redis_client: Redis client instance (or compatible mock).
        event_id: The Razorpay event identifier from the X-Razorpay-Event-Id header.

    Returns:
        True if this event_id has already been seen, False otherwise.
    """
    if not event_id:
        return False

    key = f"{IDEMPOTENCY_KEY_PREFIX}{event_id}"
    existing = redis_client.get(key)
    return existing is not None


def mark_event_processed(
    redis_client: RedisQueueClient,
    event_id: str,
) -> None:
    """Mark a webhook event as processed for idempotency.

    Args:
        redis_client: Redis client instance (or compatible mock).
        event_id: The Razorpay event identifier.
    """
    if not event_id:
        return

    key = f"{IDEMPOTENCY_KEY_PREFIX}{event_id}"
    redis_client.set(key, "1", ex=IDEMPOTENCY_TTL_SECONDS)


def enqueue_webhook_event(
    redis_client: RedisQueueClient,
    event_data: Dict[str, Any],
    queue_name: str = WEBHOOK_QUEUE_NAME,
) -> int:
    """Push a verified webhook event onto the Redis queue.

    Args:
        redis_client: Redis client instance (or compatible mock).
        event_data: The parsed and verified webhook event payload.
        queue_name: The Redis list key to push onto.

    Returns:
        The new length of the queue after the push.
    """
    serialized = json.dumps(event_data, separators=(",", ":"))
    queue_length = redis_client.lpush(queue_name, serialized)
    logger.info(
        "Enqueued webhook event to '%s' (queue length: %d)",
        queue_name,
        queue_length,
    )
    return queue_length


def pop_webhook_event(
    redis_client: RedisQueueClient,
    queue_name: str = WEBHOOK_QUEUE_NAME,
) -> Optional[Dict[str, Any]]:
    """Pop and deserialize a webhook event from the Redis queue.

    Args:
        redis_client: Redis client instance.
        queue_name: The Redis list key to pop from.

    Returns:
        The deserialized event dictionary, or None if the queue is empty.
    """
    if not hasattr(redis_client, "rpop"):
        logger.warning("Redis client does not support rpop")
        return None

    raw = redis_client.rpop(queue_name)
    if not raw:
        return None
    try:
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception as exc:
        logger.error("Failed to deserialize event from queue '%s': %s", queue_name, exc)
        return None
