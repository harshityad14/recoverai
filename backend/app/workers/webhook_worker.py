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
from app.models.retry_history import RetryHistory
from app.models.transaction import Transaction
from app.repositories.customer_repository import CustomerRepository
from app.schemas.action import ActionResult
from app.schemas.safety import GuardDecision, SafetyDecision, SafetyRuleId
from app.schemas.transaction import TransactionStatus
from app.services.action_executor import ActionExecutor
from app.services.analysis_service import AnalysisService
from app.services.llm.decision_engine import DecisionEngine
from app.services.llm.schemas import RecoveryAction, RecoveryDecision
from app.services.safety_guard import SafetyGuard

logger = logging.getLogger(__name__)


class WebhookWorker:
    """Worker for processing queued Razorpay webhook events from Redis."""

    def __init__(
        self,
        redis_client: Optional[RedisQueueClient] = None,
        db: Optional[Session] = None,
        queue_name: str = WEBHOOK_QUEUE_NAME,
        decision_engine: Optional[DecisionEngine] = None,
        safety_guard: Optional[SafetyGuard] = None,
        action_executor: Optional[ActionExecutor] = None,
        auto_recover: Optional[bool] = None,
    ):
        """Initialize the webhook worker.

        Args:
            redis_client: Optional Redis client (defaults to global redis_client).
            db: Optional SQLAlchemy Session (defaults to creating new sessions).
            queue_name: Redis queue key name to consume from.
            decision_engine: Optional DecisionEngine for AI recovery recommendations.
            safety_guard: Optional SafetyGuard for deterministic verification.
            action_executor: Optional ActionExecutor for executing authorized recovery actions.
            auto_recover: If True, executes end-to-end recovery pipeline even if decision_engine was not injected.
        """
        self.redis_client = redis_client or get_redis()
        self.db = db
        self.queue_name = queue_name
        self.analysis_service = AnalysisService(db=db)
        self.decision_engine = decision_engine
        self.safety_guard = safety_guard or SafetyGuard()
        self.action_executor = action_executor or ActionExecutor(db=db)
        self.auto_recover = auto_recover

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
        """Route payment.failed event through analysis or end-to-end recovery pipeline."""
        if self.decision_engine is not None or self.auto_recover is True:
            return self.process_failed_payment(event_data, event_id)

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

    def process_failed_payment(
        self,
        event_data: Dict[str, Any],
        event_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Execute the end-to-end recovery pipeline for a failed payment.

        Pipeline Stages:
        1. Validate & normalize event via AnalysisService
        2. Transaction lookup from database
        3. Lifecycle state & idempotency verification
        4. Recovery eligibility evaluation:
           - Ineligible: Stop without calling Gemini or ActionExecutor; persist STOP audit.
        5. Gemini Decision Engine: Produce advisory RecoveryDecision
        6. Deterministic Safety Guard: Validate against hard business rules -> SafetyDecision
        7. Action Executor: Execute authorized action via Razorpay Test Mode (receives ONLY SafetyDecision)
        8. Audit Trail & Outcome Tracking: Record complete trace in RetryHistory

        Args:
            event_data: Razorpay payment.failed webhook event dictionary.
            event_id: Optional Razorpay webhook event identifier.

        Returns:
            Dict[str, Any]: Structured execution outcome report.
        """
        # ── 1. Analysis ──
        try:
            analysis = self.analysis_service.analyze_payment_failure(event_data)
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

        db = self._get_db()
        should_close_db = self.db is None

        try:
            repo = CustomerRepository(db)
            txn = repo.get_transaction_by_payment_id(analysis.razorpay_payment_id)
            if not txn:
                txn = db.query(Transaction).filter(Transaction.id == analysis.transaction_id).first()

            if not txn:
                return {
                    "status": "processing_error",
                    "event_type": "payment.failed",
                    "event_id": event_id,
                    "error": f"Transaction not found for payment {analysis.razorpay_payment_id}",
                }

            txn_id = txn.id

            # ── 2. Terminal State Check ──
            if txn.status in (TransactionStatus.CAPTURED.value, TransactionStatus.RECOVERED.value):
                logger.info("Transaction %s already in terminal state %s; ignoring recovery", txn_id, txn.status)
                return {
                    "status": "already_terminal",
                    "event_type": "payment.failed",
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "transaction_status": txn.status,
                    "recovery_executed": False,
                }

            # ── 3. Idempotency Check for existing Payment Link ──
            if txn.payment_link_id and txn.status == TransactionStatus.RECOVERY_PENDING.value:
                logger.info(
                    "Transaction %s already has active payment link %s; idempotent return",
                    txn_id,
                    txn.payment_link_id,
                )
                return {
                    "status": "recovery_pending",
                    "event_type": "payment.failed",
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "transaction_status": txn.status,
                    "payment_link_id": txn.payment_link_id,
                    "payment_link_url": txn.payment_link_url,
                    "idempotent": True,
                    "recovery_executed": False,
                }

            # ── 4. Eligibility Check ──
            eligible = analysis.recovery_context.get("eligible_for_analysis", False)
            if not eligible:
                logger.info(
                    "Transaction %s not eligible for AI recovery (category=%s, flags=%s); halting pipeline",
                    txn_id,
                    analysis.failure_category,
                    analysis.active_risk_flags,
                )
                # Deterministic Safety verdict for ineligible failure: STOP
                # (do NOT call Gemini, do NOT call ActionExecutor)
                safety_decision = self.safety_guard.evaluate(
                    transaction_status=txn,
                    analysis=analysis,
                    customer_history=None,
                    recovery_decision=None,
                )

                if txn.status not in (
                    TransactionStatus.CAPTURED.value,
                    TransactionStatus.RECOVERED.value,
                    TransactionStatus.STOPPED.value,
                ):
                    txn.status = TransactionStatus.STOPPED.value

                # Persist STOP audit record
                existing_retries = len(txn.retry_history) if txn.retry_history else 0
                retry_record = RetryHistory(
                    transaction_id=txn.id,
                    attempt_number=existing_retries + 1,
                    action=RecoveryAction.STOP.value,
                    result="STOPPED",
                    safety_decision=safety_decision.decision.value,
                    safety_rule_id=safety_decision.rule_id.value,
                    final_action=RecoveryAction.STOP.value,
                    execution_result="STOPPED",
                    error_message=safety_decision.reason,
                )
                db.add(retry_record)
                db.commit()
                db.refresh(txn)

                return {
                    "status": "ineligible_stopped",
                    "event_type": "payment.failed",
                    "event_id": event_id,
                    "transaction_id": txn_id,
                    "transaction_status": txn.status,
                    "safety_decision": safety_decision.model_dump(),
                    "recovery_executed": False,
                    "analysis": analysis.model_dump(),
                }

            # ── 5. Decision Engine ──
            customer_history = repo.get_customer_history(
                customer_id=analysis.customer_id,
                current_payment_id=analysis.razorpay_payment_id,
            )
            existing_retries = len(txn.retry_history) if txn.retry_history else 0
            engine = self.decision_engine or DecisionEngine()

            recovery_decision = engine.recommend_action(analysis)

            # ── 6. Deterministic Safety Guard ──
            safety_decision = self.safety_guard.evaluate(
                transaction_status=txn,
                analysis=analysis,
                customer_history=customer_history,
                recovery_decision=recovery_decision,
                retry_attempts=existing_retries,
            )

            # ── 7. Action Executor (Receives ONLY SafetyDecision) ──
            action_result = self.action_executor.execute(
                transaction=txn,
                safety_decision=safety_decision,
                db=db,
            )

            # ── 8. Outcome Tracking & Audit Trail Persistence ──
            attempt_num = existing_retries + 1
            retry_record = None
            if action_result.external_id:
                retry_record = (
                    db.query(RetryHistory)
                    .filter(
                        RetryHistory.transaction_id == txn.id,
                        RetryHistory.external_id == action_result.external_id,
                    )
                    .first()
                )

            if not retry_record:
                retry_record = RetryHistory(
                    transaction_id=txn.id,
                    attempt_number=attempt_num,
                    action=safety_decision.final_action.value,
                )
                db.add(retry_record)

            # Populate complete audit fields
            retry_record.recommended_action = recovery_decision.action.value
            retry_record.confidence = recovery_decision.confidence
            retry_record.ai_rationale = recovery_decision.rationale
            retry_record.safety_decision = safety_decision.decision.value
            retry_record.safety_rule_id = safety_decision.rule_id.value
            retry_record.final_action = safety_decision.final_action.value
            retry_record.execution_result = (
                "SUCCESS" if action_result.success else (action_result.error_code or "FAILED")
            )
            retry_record.result = (
                "LINK_CREATED"
                if safety_decision.final_action == RecoveryAction.PAYMENT_LINK and action_result.success
                else ("SUCCESS" if action_result.success else (action_result.error_code or "FAILED"))
            )
            retry_record.external_id = action_result.external_id
            retry_record.error_code = action_result.error_code
            retry_record.error_message = action_result.error_message

            try:
                db.commit()
                db.refresh(txn)
            except Exception as e:
                logger.error("Failed to commit audit trail for transaction %s: %s", txn_id, e)
                db.rollback()

            return {
                "status": "processed",
                "event_type": "payment.failed",
                "event_id": event_id,
                "transaction_id": txn.id,
                "transaction_status": txn.status,
                "analysis": analysis.model_dump(),
                "recovery_decision": recovery_decision.model_dump(),
                "safety_decision": safety_decision.model_dump(),
                "action_result": action_result.model_dump(),
                "recovery_executed": action_result.success,
            }

        finally:
            if should_close_db:
                db.close()

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
            notes = payment_entity.get("notes") or {}
            payment_link_id = (
                payment_entity.get("payment_link_id")
                or notes.get("payment_link_id")
                if isinstance(notes, dict)
                else None
            )

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
                        payment_link_id=payment_link_id,
                        notes=notes if isinstance(notes, dict) else None,
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
