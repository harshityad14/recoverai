"""Payment Analysis Service.

Coordinates failure classification, customer context retrieval, recovery eligibility
assessment, and transaction persistence to produce normalized analysis outputs
for downstream recovery evaluation.
"""

import logging
from typing import Any, Dict, Optional
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.repositories.customer_repository import CustomerRepository
from app.schemas.analysis import PaymentAnalysis
from app.schemas.taxonomy import FailureCategory
from app.services.failure_classifier import FailureClassifier

logger = logging.getLogger(__name__)

# Blocking risk flags that disqualify a transaction from autonomous recovery
BLOCKING_RISK_FLAGS = {
    "FRAUD_SUSPICION",
    "BLACKLISTED",
    "CHARGEBACK_HISTORY",
    "HIGH_RISK_CUSTOMER",
    "SECURITY_VIOLATION",
}


class AnalysisService:
    """Service responsible for normalizing and analyzing payment failure events."""

    def __init__(self, db: Optional[Session] = None):
        """Initialize with an optional database session.

        Args:
            db: Optional SQLAlchemy Session. If not provided, a session will be created.
        """
        self._db = db

    def _get_db(self) -> Session:
        """Get or create database session."""
        if self._db is not None:
            return self._db
        return SessionLocal()

    @staticmethod
    def extract_payment_entity(event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Extract the payment entity from a webhook event or raw payment payload.

        Handles both top-level event structures and nested webhook event envelopes.

        Args:
            event_data: Webhook event dictionary or payment entity.

        Returns:
            Dict[str, Any]: Extracted payment entity dictionary.

        Raises:
            ValueError: If the event data is malformed or does not contain a payment entity.
        """
        if not event_data or not isinstance(event_data, dict):
            raise ValueError("Invalid event data: expected non-empty dictionary")

        # Case 1: Standard Razorpay webhook payload structure
        # payload.payment.entity
        payload = event_data.get("payload")
        if isinstance(payload, dict):
            payment = payload.get("payment")
            if isinstance(payment, dict):
                entity = payment.get("entity")
                if isinstance(entity, dict):
                    return entity

        # Case 2: Enqueued worker structure: {"event_id": ..., "payload": {...}}
        if "payload" in event_data and isinstance(event_data["payload"], dict):
            inner_payload = event_data["payload"].get("payload")
            if isinstance(inner_payload, dict):
                payment = inner_payload.get("payment")
                if isinstance(payment, dict):
                    entity = payment.get("entity")
                    if isinstance(entity, dict):
                        return entity

        # Case 3: Already unwrapped payment entity with 'entity': 'payment' or 'id'
        if event_data.get("entity") == "payment" or (
            "id" in event_data and str(event_data["id"]).startswith("pay_")
        ):
            return event_data

        raise ValueError("Could not extract payment entity from event data")

    def analyze_payment_failure(
        self,
        event_data: Dict[str, Any],
        allow_demo_fallback: bool = True,
    ) -> PaymentAnalysis:
        """Analyze a verified Razorpay payment.failed webhook event.

        Performs:
        1. Payment entity extraction and validation
        2. Deterministic failure classification
        3. Customer identification and context retrieval (24h attempts, success rate, flags)
        4. Recovery eligibility computation
        5. Database transaction persistence
        6. Normalized Pydantic analysis generation

        Args:
            event_data: Razorpay webhook event payload.
            allow_demo_fallback: Allow synthetic demo customer IDs from notes if present.

        Returns:
            PaymentAnalysis: Normalized analysis output.

        Raises:
            ValueError: If required payment fields are missing or payload is unparseable.
        """
        # 1. Extract payment entity
        payment_entity = self.extract_payment_entity(event_data)

        payment_id = payment_entity.get("id")
        if not payment_id:
            raise ValueError("Payment entity is missing required 'id' field")

        raw_amount = payment_entity.get("amount")
        if raw_amount is None:
            raise ValueError(f"Payment entity {payment_id} is missing required 'amount' field")

        try:
            amount = int(raw_amount)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid amount value '{raw_amount}' for payment {payment_id}")

        currency = str(payment_entity.get("currency") or "INR")
        order_id = payment_entity.get("order_id")
        payment_method = payment_entity.get("method")
        error_code = payment_entity.get("error_code")
        error_description = payment_entity.get("error_description")

        # 2. Deterministic failure classification
        failure_category = FailureClassifier.classify_payment_entity(payment_entity)

        # 3. Customer context extraction & database operations
        db = self._get_db()
        should_close_db = self._db is None

        try:
            repo = CustomerRepository(db)
            customer_id = repo.extract_customer_id(
                payment_entity,
                allow_demo_fallback=allow_demo_fallback,
            )

            # Retrieve customer history excluding this payment
            customer_history = repo.get_customer_history(
                customer_id=customer_id,
                current_payment_id=payment_id,
            )

            # Check if this transaction already exists and was captured or recovered
            existing_txn = repo.get_transaction_by_payment_id(payment_id)
            is_already_captured = (
                existing_txn is not None and existing_txn.status in ("CAPTURED", "RECOVERED")
            )
            is_already_recovered = (
                existing_txn is not None and existing_txn.status == "RECOVERED"
            )

            # 4. Compute recovery eligibility context
            has_blocking_risk = any(
                flag in BLOCKING_RISK_FLAGS for flag in customer_history.active_risk_flags
            )
            is_fraud = failure_category == FailureCategory.FRAUD_RISK

            # Eligible if:
            # - not already captured or recovered
            # - not classified as fraud
            # - does not have active blocking risk flags
            # - amount is positive
            eligible_for_analysis = (
                not is_already_captured
                and not is_fraud
                and not has_blocking_risk
                and amount > 0
            )

            recovery_context = {
                "eligible_for_analysis": eligible_for_analysis,
                "is_already_captured": is_already_captured,
                "is_already_recovered": is_already_recovered,
                "has_active_risk_flags": len(customer_history.active_risk_flags) > 0,
                "total_previous_attempts": customer_history.total_attempts,
                "previous_failed_payments": customer_history.previous_failed_payments,
                "is_transient_failure": failure_category
                in (
                    FailureCategory.BANK_TIMEOUT,
                    FailureCategory.PAYMENT_TIMEOUT,
                    FailureCategory.NETWORK_ERROR,
                ),
                "requires_step_up_auth": failure_category
                in (
                    FailureCategory.THREE_DS_FAILURE,
                    FailureCategory.AUTHENTICATION_FAILURE,
                ),
            }

            # 5. Persist transaction in database
            persisted_txn = repo.upsert_failed_transaction(
                razorpay_payment_id=payment_id,
                amount=amount,
                currency=currency,
                razorpay_order_id=order_id,
                customer_id=customer_id,
                payment_method=payment_method,
                failure_category=failure_category.value,
                failure_code=error_code,
                failure_description=error_description,
            )
            transaction_id = persisted_txn.id

            logger.info(
                "Analyzed failed payment: id=%s, txn_id=%s, category=%s, eligible=%s",
                payment_id,
                transaction_id,
                failure_category.value,
                eligible_for_analysis,
            )

            # 6. Return normalized analysis object
            return PaymentAnalysis(
                transaction_id=transaction_id,
                razorpay_payment_id=payment_id,
                razorpay_order_id=order_id,
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                failure_category=failure_category.value,
                failure_code=error_code,
                failure_description=error_description,
                attempt_count_24h=customer_history.attempt_count_24h,
                previous_successful_payments=customer_history.previous_successful_payments,
                active_risk_flags=customer_history.active_risk_flags,
                recovery_context=recovery_context,
            )
        finally:
            if should_close_db:
                db.close()
