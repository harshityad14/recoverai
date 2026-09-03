"""Redis Webhook Worker.

Consumes verified webhook events from the Redis queue, safely deserializes payloads,
routes failure events to the Payment Analysis Service, and acknowledges captured
payments without triggering recovery workflows (preparing for the future Outcome Tracker).
"""

import json
import logging
import time
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.core.queue import WEBHOOK_QUEUE_NAME, RedisQueueClient
from app.core.redis import get_redis
from app.repositories.customer_repository import CustomerRepository
from app.services.analysis_service import AnalysisService

logger = logging.getLogger(__name__)


class WebhookWorker:
    """Worker for processing queued Razorpay webhook events from Redis."""

    def __init__(
        self,
        redis_client: Optional[RedisQueueClient] = None,
        db: Optional[Session] = None,
        queue_name: str = WEBHOOK_QUEUE_NAME,
    ):
        """Initialize the webhook worker.

        Args:
            redis_client: Optional Redis client (defaults to global redis_client).
            db: Optional SQLAlchemy Session (defaults to creating new sessions).
            queue_name: Redis queue key name to consume from.
        """
        self.redis_client = redis_client or get_redis()
        self.db = db
        self.queue_name = queue_name
        self.analysis_service = AnalysisService(db=db)

    def _get_db(self) -> Session:
        """Get or create database session."""
        if self.db is not None:
            return self.db
        return SessionLocal()

    def process_raw_message(self, raw_message: Any) -> Dict[str, Any]:
        """Safely deserialize and process a single message from the queue.

        Guaranteed not to raise unhandled exceptions; resilient against
        malformed JSON, invalid structures, or unexpected payload shapes.

        Args:
            raw_message: Raw string or bytes popped from Redis.

        Returns:
            Dict[str, Any]: Result summary with status and metadata.
        """
        if raw_message is None:
            return {"status": "empty", "message": "No message provided"}

        # ── 1. Safe Deserialization ──
        try:
            if isinstance(raw_message, (bytes, bytearray)):
                raw_message = raw_message.decode("utf-8")

            if isinstance(raw_message, str):
                event_data = json.loads(raw_message)
            elif isinstance(raw_message, dict):
                event_data = raw_message
            else:
                logger.warning("Unrecognized message type: %s", type(raw_message))
                return {"status": "error", "error": "Invalid message format"}
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            logger.error("Malformed JSON in queue message: %s", exc)
            return {"status": "malformed_json", "error": str(exc)}
        except Exception as exc:
            logger.error("Unexpected error deserializing queue message: %s", exc)
            return {"status": "deserialization_error", "error": str(exc)}

        if not isinstance(event_data, dict):
            logger.warning("Queue event payload is not a dictionary: %s", type(event_data))
            return {"status": "error", "error": "Payload is not a JSON object"}

        # ── 2. Determine Event Type ──
        # Event type can be in event_type (enqueued wrapper) or event (direct payload)
        event_type = (
            event_data.get("event_type")
            or event_data.get("event")
            or (
                event_data.get("payload", {}).get("event")
                if isinstance(event_data.get("payload"), dict)
                else None
            )
        )

        event_id = event_data.get("event_id")

        if not event_type:
            logger.warning("Queue message missing event type: %s", event_data.keys())
            return {"status": "missing_event_type", "error": "No event type found"}

        # ── 3. Route by Event Type ──
        if event_type == "payment.failed":
            return self._handle_payment_failed(event_data, event_id)
        elif event_type == "payment.captured":
            return self._handle_payment_captured(event_data, event_id)
        else:
            logger.info("Ignoring unsupported queued event type: %s", event_type)
            return {"status": "ignored", "event_type": event_type}

    def _handle_payment_failed(
        self,
        event_data: Dict[str, Any],
        event_id: Optional[str],
    ) -> Dict[str, Any]:
        """Process a payment.failed event via the Analysis Service."""
        try:
            analysis = self.analysis_service.analyze_payment_failure(event_data)
            logger.info(
                "Successfully analyzed failed payment %s (category=%s, eligible=%s)",
                analysis.razorpay_payment_id,
                analysis.failure_category,
                analysis.recovery_context.get("eligible_for_analysis"),
            )
            return {
                "status": "analyzed",
                "event_type": "payment.failed",
                "event_id": event_id,
                "analysis": analysis.model_dump(),
            }
        except ValueError as exc:
            logger.warning("Validation error analyzing failed payment: %s", exc)
            return {
                "status": "validation_error",
                "event_type": "payment.failed",
                "event_id": event_id,
                "error": str(exc),
            }
        except Exception as exc:
            logger.error("Error analyzing failed payment: %s", exc, exc_info=True)
            return {
                "status": "processing_error",
                "event_type": "payment.failed",
                "event_id": event_id,
                "error": str(exc),
            }

    def _handle_payment_captured(
        self,
        event_data: Dict[str, Any],
        event_id: Optional[str],
    ) -> Dict[str, Any]:
        """Acknowledge and track a payment.captured event without triggering recovery."""
        try:
            # Extract payment entity safely
            payment_entity = AnalysisService.extract_payment_entity(event_data)
            payment_id = payment_entity.get("id")
            order_id = payment_entity.get("order_id")
            amount = payment_entity.get("amount")
            currency = payment_entity.get("currency") or "INR"
            method = payment_entity.get("method")

            db = self._get_db()
            should_close_db = self.db is None

            try:
                repo = CustomerRepository(db)
                customer_id = repo.extract_customer_id(payment_entity, allow_demo_fallback=True)

                if payment_id:
                    updated_txn = repo.mark_transaction_captured(
                        razorpay_payment_id=payment_id,
                        razorpay_order_id=order_id,
                        amount=int(amount) if amount is not None else None,
                        currency=str(currency),
                        payment_method=method,
                        customer_id=customer_id,
                    )
                    txn_id = updated_txn.id if updated_txn else None
                    txn_status = updated_txn.status if updated_txn else "CAPTURED"
                else:
                    txn_id = None
                    txn_status = None

                logger.info(
                    "Acknowledged payment.captured for payment_id=%s (txn_id=%s, status=%s). No recovery triggered.",
                    payment_id,
                    txn_id,
                    txn_status,
                )

                return {
                    "status": "acknowledged",
                    "event_type": "payment.captured",
                    "event_id": event_id,
                    "payment_id": payment_id,
                    "transaction_id": txn_id,
                    "transaction_status": txn_status,
                    "recovery_triggered": False,
                }
            finally:
                if should_close_db:
                    db.close()

        except Exception as exc:
            logger.warning("Error processing payment.captured acknowledgment: %s", exc)
            return {
                "status": "captured_acknowledged_with_warning",
                "event_type": "payment.captured",
                "event_id": event_id,
                "error": str(exc),
                "recovery_triggered": False,
            }

    def pop_and_process(self) -> Optional[Dict[str, Any]]:
        """Pop a single event from Redis queue and process it.

        Uses RPOP to ensure FIFO consumption matching LPUSH ingestion.

        Returns:
            Optional[Dict[str, Any]]: Result of processing, or None if queue is empty/unavailable.
        """
        if not self.redis_client:
            logger.warning("Redis client unavailable for pop_and_process")
            return None

        try:
            # Check if redis_client supports rpop
            if hasattr(self.redis_client, "rpop"):
                raw_message = self.redis_client.rpop(self.queue_name)
            else:
                # Fallback for minimal mocks: check if lrange and delete or pop
                logger.warning("Redis client does not support rpop")
                return None

            if raw_message is None:
                return None

            return self.process_raw_message(raw_message)
        except Exception as exc:
            logger.error("Error popping or processing item from queue: %s", exc)
            return {"status": "error", "error": str(exc)}

    def run(
        self,
        max_iterations: Optional[int] = None,
        poll_interval_seconds: float = 1.0,
        stop_event: Optional[Any] = None,
    ) -> int:
        """Run the worker loop.

        Args:
            max_iterations: Maximum loop cycles before terminating (useful for testing).
            poll_interval_seconds: Seconds to sleep when the queue is empty.
            stop_event: Optional threading.Event or object with is_set() method.

        Returns:
            int: Number of events successfully processed.
        """
        logger.info("Starting WebhookWorker on queue '%s'", self.queue_name)
        processed_count = 0
        iterations = 0

        while True:
            if stop_event and stop_event.is_set():
                logger.info("Stop event received. Terminating WebhookWorker.")
                break

            if max_iterations is not None and iterations >= max_iterations:
                logger.info("Reached max iterations (%d). Terminating worker.", max_iterations)
                break

            iterations += 1

            try:
                result = self.pop_and_process()
                if result is not None:
                    processed_count += 1
                else:
                    # Queue is empty; back off briefly
                    if poll_interval_seconds > 0:
                        time.sleep(poll_interval_seconds)
            except Exception as exc:
                logger.error("Unexpected error in worker loop iteration: %s", exc)
                time.sleep(poll_interval_seconds)

        logger.info("WebhookWorker finished. Processed %d events.", processed_count)
        return processed_count
