"""Action Executor Service for Razorpay Test Mode.

Executes permitted recovery actions authorized ONLY by the deterministic Safety Guard.

CORE PRINCIPLES:
- Safety Guard is the final authority.
- Action Executor must NEVER execute raw Gemini recommendations.
- Payment Link created != payment recovered. Transactions transition to RECOVERY_PENDING.
- Idempotent: existing active payment links are preserved without duplicate API calls.
- Safe unsupported handling for RETRY and REMINDER (never inventing fake endpoints).
- Live Mode is strictly prohibited.
"""

from datetime import datetime, timezone
import logging
from typing import Any, Optional
from sqlalchemy.orm import Session

from app.models.retry_history import RetryHistory
from app.models.transaction import Transaction
from app.schemas.action import ActionResult
from app.schemas.safety import GuardDecision, SafetyDecision
from app.schemas.transaction import TransactionStatus
from app.services.llm.schemas import RecoveryAction
from app.services.razorpay_client import (
    RazorpayAPIError,
    RazorpayAuthenticationError,
    RazorpayClient,
    RazorpayClientError,
    RazorpayNetworkError,
    RazorpayResponseError,
    RazorpaySecurityError,
    RazorpayTimeoutError,
)

logger = logging.getLogger(__name__)


class ActionExecutor:
    """Dispatches authorized recovery actions against Razorpay Test Mode."""

    def __init__(
        self,
        razorpay_client: Optional[RazorpayClient] = None,
        db: Optional[Session] = None,
    ):
        """Initialize ActionExecutor.

        Args:
            razorpay_client: Injected RazorpayClient instance. If None, creates default.
            db: Optional database session for persisting execution results.
        """
        self.razorpay_client = razorpay_client or RazorpayClient()
        self.db = db

    def execute(
        self,
        transaction: Transaction,
        safety_decision: Any,
        db: Optional[Session] = None,
    ) -> ActionResult:
        """Execute the recovery action authorized by the Safety Guard.

        Args:
            transaction: The RecoverAI Transaction model instance.
            safety_decision: Authoritative SafetyDecision produced by SafetyGuard.
            db: Optional SQLAlchemy Session (overrides instance db if provided).

        Returns:
            ActionResult: Strongly-typed, structured outcome of the execution attempt.
        """
        active_db = db or self.db
        txn_id = getattr(transaction, "id", "unknown")

        # ── 1. Input Verification: Must be a SafetyDecision ──
        if not isinstance(safety_decision, SafetyDecision):
            logger.error(
                "ActionExecutor received untrusted input of type %s for transaction %s",
                type(safety_decision),
                txn_id,
            )
            return ActionResult(
                success=False,
                action=RecoveryAction.STOP,
                transaction_id=txn_id,
                error_code="UNAUTHORIZED_DECISION_INPUT",
                error_message="ActionExecutor requires an authoritative SafetyDecision. Raw LLM input is prohibited.",
                timestamp=datetime.now(timezone.utc),
            )

        decision = safety_decision.decision
        final_action = safety_decision.final_action

        logger.info(
            "ActionExecutor evaluating decision=%s, action=%s for transaction %s",
            decision.value,
            final_action.value,
            txn_id,
        )

        # ── 2. STOP Actions (APPROVE + STOP or OVERRIDE + STOP) ──
        if final_action == RecoveryAction.STOP:
            if decision in (GuardDecision.APPROVE, GuardDecision.OVERRIDE):
                logger.info(
                    "Safety Guard mandated STOP for transaction %s; performing no external recovery",
                    txn_id,
                )
                if active_db and transaction.status not in (
                    TransactionStatus.CAPTURED.value,
                    TransactionStatus.RECOVERED.value,
                    TransactionStatus.STOPPED.value,
                ):
                    transaction.status = TransactionStatus.STOPPED.value
                    try:
                        active_db.commit()
                        active_db.refresh(transaction)
                    except Exception as e:
                        logger.warning("Failed to update transaction %s status to STOPPED: %s", txn_id, e)

                return ActionResult(
                    success=True,
                    action=RecoveryAction.STOP,
                    transaction_id=txn_id,
                    timestamp=datetime.now(timezone.utc),
                    details={"message": "No external action performed; recovery stopped by Safety Guard."},
                )

            return ActionResult(
                success=False,
                action=RecoveryAction.STOP,
                transaction_id=txn_id,
                error_code="UNEXPECTED_DECISION_COMBINATION",
                error_message=f"Unauthorized decision combination: {decision.value} + STOP",
                timestamp=datetime.now(timezone.utc),
            )

        # ── 3. Validate Authorized Active Recovery Combinations ──
        if decision != GuardDecision.APPROVE:
            logger.warning(
                "ActionExecutor rejected non-APPROVE decision '%s' for action '%s' on transaction %s",
                decision.value,
                final_action.value,
                txn_id,
            )
            return ActionResult(
                success=False,
                action=final_action,
                transaction_id=txn_id,
                error_code="UNEXPECTED_DECISION_COMBINATION",
                error_message=f"ActionExecutor rejected unauthorized decision combination: {decision.value} + {final_action.value}",
                timestamp=datetime.now(timezone.utc),
            )

        # ── 4. RETRY Action Handling (Safe Unsupported Implementation) ──
        if final_action == RecoveryAction.RETRY:
            logger.info(
                "Automated server-side card retry requested for transaction %s; returning ACTION_NOT_SUPPORTED",
                txn_id,
            )
            return ActionResult(
                success=False,
                action=RecoveryAction.RETRY,
                transaction_id=txn_id,
                error_code="ACTION_NOT_SUPPORTED",
                error_message="Direct automated card retry is not supported by Razorpay API; requires customer re-attempt or payment link.",
                timestamp=datetime.now(timezone.utc),
            )

        # ── 5. REMINDER Action Handling (Safe Unsupported Implementation) ──
        if final_action == RecoveryAction.REMINDER:
            logger.info(
                "Standalone customer reminder requested for transaction %s; returning NOT_IMPLEMENTED",
                txn_id,
            )
            return ActionResult(
                success=False,
                action=RecoveryAction.REMINDER,
                transaction_id=txn_id,
                error_code="NOT_IMPLEMENTED",
                error_message="Standalone customer reminder without active payment link is not supported by Razorpay API.",
                timestamp=datetime.now(timezone.utc),
            )

        # ── 6. PAYMENT_LINK Action Execution ──
        if final_action == RecoveryAction.PAYMENT_LINK:
            return self._execute_payment_link(transaction, active_db)

        # ── 7. Catch-all for any unrecognized action ──
        return ActionResult(
            success=False,
            action=final_action,
            transaction_id=txn_id,
            error_code="UNEXPECTED_DECISION_COMBINATION",
            error_message=f"Unrecognized recovery action: {final_action.value}",
            timestamp=datetime.now(timezone.utc),
        )

    def _execute_payment_link(
        self,
        transaction: Transaction,
        db: Optional[Session],
    ) -> ActionResult:
        """Create and store a Razorpay Payment Link in Test Mode."""
        txn_id = transaction.id

        # Check transaction state: must be recoverable
        if transaction.status in (
            TransactionStatus.CAPTURED.value,
            TransactionStatus.RECOVERED.value,
            TransactionStatus.STOPPED.value,
        ):
            logger.warning(
                "Cannot execute payment link on transaction %s with terminal status '%s'",
                txn_id,
                transaction.status,
            )
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code="TRANSACTION_NOT_RECOVERABLE",
                error_message=f"Transaction is in terminal state '{transaction.status}'; recovery aborted.",
                timestamp=datetime.now(timezone.utc),
            )

        # Idempotency Check: if payment link already exists, return existing link
        if transaction.payment_link_id:
            logger.info(
                "Payment link %s already exists for transaction %s; returning existing link",
                transaction.payment_link_id,
                txn_id,
            )
            return ActionResult(
                success=True,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                external_id=transaction.payment_link_id,
                payment_link_url=transaction.payment_link_url,
                idempotent=True,
                timestamp=datetime.now(timezone.utc),
                details={"message": "Reused existing active payment link."},
            )

        # Generate unique reference ID
        existing_retries = len(transaction.retry_history) if transaction.retry_history else 0
        attempt_num = existing_retries + 1
        payment_suffix = (transaction.razorpay_payment_id or "pay")[-8:]
        reference_id = f"rec_{txn_id[:8]}_{payment_suffix}_{attempt_num}"

        # Construct customer payload if identifier is contact/email
        customer_payload: Optional[dict] = None
        if transaction.customer_id and "@" in transaction.customer_id:
            customer_payload = {"email": transaction.customer_id}
        elif transaction.customer_id and transaction.customer_id.isdigit():
            customer_payload = {"contact": transaction.customer_id}

        notes = {
            "transaction_id": str(txn_id),
            "original_payment_id": str(transaction.razorpay_payment_id),
            "recovered_by": "RecoverAI",
        }

        # Dispatch API request via RazorpayClient
        try:
            link_data = self.razorpay_client.create_payment_link(
                amount=transaction.amount,
                currency=transaction.currency or "INR",
                reference_id=reference_id,
                description=f"RecoverAI payment recovery for payment {transaction.razorpay_payment_id}",
                customer=customer_payload,
                notes=notes,
                reminder_enable=True,
            )
        except RazorpaySecurityError as exc:
            logger.critical("Security violation executing payment link: %s", exc)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code=exc.error_code,
                error_message=str(exc),
                timestamp=datetime.now(timezone.utc),
            )
        except RazorpayAuthenticationError as exc:
            logger.error("Authentication failure creating payment link for txn %s: %s", txn_id, exc)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code=exc.error_code,
                error_message="Razorpay authentication failed.",
                timestamp=datetime.now(timezone.utc),
            )
        except RazorpayTimeoutError as exc:
            logger.error("Timeout creating payment link for txn %s: %s", txn_id, exc)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code=exc.error_code,
                error_message="Razorpay API timed out during link creation.",
                timestamp=datetime.now(timezone.utc),
            )
        except RazorpayNetworkError as exc:
            logger.error("Network failure creating payment link for txn %s: %s", txn_id, exc)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code=exc.error_code,
                error_message="Network error communicating with Razorpay API.",
                timestamp=datetime.now(timezone.utc),
            )
        except RazorpayResponseError as exc:
            logger.error("Invalid response creating payment link for txn %s: %s", txn_id, exc)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code=exc.error_code,
                error_message="Malformed response from Razorpay API.",
                timestamp=datetime.now(timezone.utc),
            )
        except RazorpayAPIError as exc:
            logger.warning("API error creating payment link for txn %s: %s", txn_id, exc)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code=exc.error_code,
                error_message=exc.error_description or str(exc),
                timestamp=datetime.now(timezone.utc),
            )
        except Exception as exc:
            logger.error("Unexpected error creating payment link for txn %s: %s", txn_id, exc, exc_info=True)
            return ActionResult(
                success=False,
                action=RecoveryAction.PAYMENT_LINK,
                transaction_id=txn_id,
                error_code="INTERNAL_EXECUTOR_ERROR",
                error_message="Unexpected error during payment link execution.",
                timestamp=datetime.now(timezone.utc),
            )

        # Extract payment link metadata
        plink_id = link_data.get("id")
        short_url = link_data.get("short_url")

        # Update transaction state in database: transition to RECOVERY_PENDING
        transaction.status = TransactionStatus.RECOVERY_PENDING.value
        transaction.payment_link_id = plink_id
        transaction.payment_link_url = short_url
        transaction.payment_link_reference_id = reference_id

        # Persist audit record in RetryHistory
        retry_record = RetryHistory(
            transaction_id=transaction.id,
            attempt_number=attempt_num,
            action=RecoveryAction.PAYMENT_LINK.value,
            result="LINK_CREATED",
            external_id=plink_id,
        )

        if db:
            try:
                db.add(retry_record)
                db.commit()
                db.refresh(transaction)
                logger.info(
                    "Persisted payment link %s for transaction %s (status=RECOVERY_PENDING)",
                    plink_id,
                    txn_id,
                )
            except Exception as exc:
                logger.error("Database error saving payment link record: %s", exc)
                db.rollback()

        return ActionResult(
            success=True,
            action=RecoveryAction.PAYMENT_LINK,
            transaction_id=txn_id,
            external_id=plink_id,
            payment_link_url=short_url,
            idempotent=False,
            timestamp=datetime.now(timezone.utc),
            details={
                "reference_id": reference_id,
                "status": link_data.get("status"),
                "created_at": link_data.get("created_at"),
            },
        )
