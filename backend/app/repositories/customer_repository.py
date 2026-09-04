"""Customer repository for querying historical payment behavior and risk context.

Interacts with PostgreSQL (or SQLite during testing) to provide customer attempt metrics,
success rates, and active risk flags for recovery decision-making.
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional
from sqlalchemy.orm import Session

from app.models.risk_flag import RiskFlag
from app.models.transaction import Transaction
from app.schemas.customer import CustomerHistorySummary

logger = logging.getLogger(__name__)


class CustomerRepository:
    """Repository layer for customer context and transaction persistence."""

    def __init__(self, db: Session):
        """Initialize with an active SQLAlchemy database session.

        Args:
            db: SQLAlchemy Session instance.
        """
        self.db = db

    @staticmethod
    def extract_customer_id(
        payment_entity: Dict[str, Any],
        allow_demo_fallback: bool = False,
    ) -> Optional[str]:
        """Safely extract customer identifier from a Razorpay payment entity.

        Checks official payment entity fields and notes.
        Does NOT invent false customer identity.
        Allows synthetic demo identifiers only if explicitly configured or provided in notes.

        Args:
            payment_entity: The payment dictionary from payload.payment.entity.
            allow_demo_fallback: If True, checks for demo notes before returning None.

        Returns:
            Optional[str]: Extracted customer identifier or None.
        """
        if not payment_entity or not isinstance(payment_entity, dict):
            return None

        # 1. Official customer_id field
        customer_id = payment_entity.get("customer_id")
        if customer_id and str(customer_id).strip():
            return str(customer_id).strip()

        # 2. Check metadata / notes
        notes = payment_entity.get("notes") or {}
        if isinstance(notes, dict):
            for key in ("customer_id", "cust_id", "user_id", "client_id"):
                val = notes.get(key)
                if val and str(val).strip():
                    return str(val).strip()

        # 3. Check contact or email as fallback customer identity
        email = payment_entity.get("email")
        if email and str(email).strip():
            return str(email).strip().lower()

        contact = payment_entity.get("contact")
        if contact and str(contact).strip():
            return str(contact).strip()

        # 4. Optional demo fallback for hackathon synthetic data
        if allow_demo_fallback and isinstance(notes, dict):
            demo_id = notes.get("demo_customer_id")
            if demo_id and str(demo_id).strip():
                return str(demo_id).strip()

        return None

    def get_customer_history(
        self,
        customer_id: Optional[str],
        current_payment_id: Optional[str] = None,
    ) -> CustomerHistorySummary:
        """Retrieve aggregated payment attempt history and active risk flags for a customer.

        Args:
            customer_id: Customer identifier string, or None.
            current_payment_id: Optional current payment ID to exclude from historical counts.

        Returns:
            CustomerHistorySummary: Context summary.
        """
        if not customer_id:
            logger.debug("No customer_id provided; returning empty customer history context")
            return CustomerHistorySummary(
                customer_id=None,
                total_attempts=0,
                attempt_count_24h=0,
                previous_successful_payments=0,
                previous_failed_payments=0,
                active_risk_flags=[],
            )

        # Query all existing transactions for this customer
        query = self.db.query(Transaction).filter(Transaction.customer_id == customer_id)
        if current_payment_id:
            query = query.filter(Transaction.razorpay_payment_id != current_payment_id)

        txns: List[Transaction] = query.all()

        now_utc = datetime.now(timezone.utc)
        cutoff_24h = now_utc - timedelta(hours=24)

        total_attempts = len(txns)
        attempt_count_24h = 0
        previous_successful = 0
        previous_recovered = 0
        previous_failed = 0

        for tx in txns:
            # 24-hour attempt count
            if tx.created_at:
                tx_time = (
                    tx.created_at
                    if tx.created_at.tzinfo
                    else tx.created_at.replace(tzinfo=timezone.utc)
                )
                if tx_time >= cutoff_24h:
                    attempt_count_24h += 1

            # Success count (CAPTURED or RECOVERED)
            status_upper = (tx.status or "").upper()
            if status_upper in ("CAPTURED", "RECOVERED"):
                previous_successful += 1
                if status_upper == "RECOVERED":
                    previous_recovered += 1
            elif status_upper == "FAILED":
                previous_failed += 1

        # Fetch active risk flags
        active_flags = self.get_active_risk_flags(customer_id)

        return CustomerHistorySummary(
            customer_id=customer_id,
            total_attempts=total_attempts,
            attempt_count_24h=attempt_count_24h,
            previous_successful_payments=previous_successful,
            previous_recovered_payments=previous_recovered,
            previous_failed_payments=previous_failed,
            active_risk_flags=active_flags,
        )

    def get_active_risk_flags(self, customer_id: str) -> List[str]:
        """Get all active risk flags associated with a customer.

        Args:
            customer_id: The customer identifier.

        Returns:
            List[str]: List of active risk flag identifiers.
        """
        if not customer_id:
            return []

        flags = (
            self.db.query(RiskFlag.flag)
            .filter(
                RiskFlag.customer_id == customer_id,
                RiskFlag.active.is_(True),
            )
            .all()
        )
        return [f[0] for f in flags]

    def add_risk_flag(
        self,
        customer_id: str,
        flag: str,
        active: bool = True,
    ) -> RiskFlag:
        """Record or update a risk flag for a customer.

        Args:
            customer_id: Customer identifier.
            flag: Risk flag name.
            active: Flag status.

        Returns:
            RiskFlag: The persisted risk flag entity.
        """
        existing = (
            self.db.query(RiskFlag)
            .filter(
                RiskFlag.customer_id == customer_id,
                RiskFlag.flag == flag,
            )
            .first()
        )
        if existing:
            existing.active = active
            self.db.commit()
            self.db.refresh(existing)
            return existing

        risk_flag = RiskFlag(
            customer_id=customer_id,
            flag=flag,
            active=active,
        )
        self.db.add(risk_flag)
        self.db.commit()
        self.db.refresh(risk_flag)
        return risk_flag

    def get_transaction_by_payment_id(
        self,
        payment_id: str,
    ) -> Optional[Transaction]:
        """Find transaction by Razorpay payment ID.

        Args:
            payment_id: The Razorpay payment ID (e.g., pay_xxxxx).

        Returns:
            Optional[Transaction]: Found transaction or None.
        """
        return (
            self.db.query(Transaction)
            .filter(Transaction.razorpay_payment_id == payment_id)
            .first()
        )

    def upsert_failed_transaction(
        self,
        razorpay_payment_id: str,
        amount: int,
        currency: str = "INR",
        razorpay_order_id: Optional[str] = None,
        customer_id: Optional[str] = None,
        payment_method: Optional[str] = None,
        failure_category: Optional[str] = None,
        failure_code: Optional[str] = None,
        failure_description: Optional[str] = None,
    ) -> Transaction:
        """Create or update a transaction record for a failed payment.

        Supports state transition rules: does not overwrite a previously RECOVERED
        transaction back to FAILED without explicit override.

        Args:
            razorpay_payment_id: Unique Razorpay payment ID.
            amount: Transaction amount in subunits.
            currency: ISO currency code.
            razorpay_order_id: Order identifier.
            customer_id: Customer identifier.
            payment_method: Payment method.
            failure_category: Normalized taxonomy category.
            failure_code: Raw Razorpay error code.
            failure_description: Human-readable error description.

        Returns:
            Transaction: The persisted transaction record.
        """
        txn = self.get_transaction_by_payment_id(razorpay_payment_id)
        if txn:
            # Preserve terminal/successful statuses (CAPTURED, RECOVERED)
            if txn.status not in ("RECOVERED", "CAPTURED"):
                txn.status = "FAILED"
            txn.failure_category = failure_category or txn.failure_category
            txn.failure_code = failure_code or txn.failure_code
            txn.failure_description = failure_description or txn.failure_description
            if customer_id and not txn.customer_id:
                txn.customer_id = customer_id
            if razorpay_order_id and not txn.razorpay_order_id:
                txn.razorpay_order_id = razorpay_order_id
            self.db.commit()
            self.db.refresh(txn)
            return txn

        txn = Transaction(
            razorpay_payment_id=razorpay_payment_id,
            razorpay_order_id=razorpay_order_id,
            customer_id=customer_id,
            amount=amount,
            currency=currency,
            payment_method=payment_method,
            status="FAILED",
            failure_category=failure_category,
            failure_code=failure_code,
            failure_description=failure_description,
        )
        self.db.add(txn)
        self.db.commit()
        self.db.refresh(txn)
        return txn

    def get_transaction_by_payment_link_id(
        self,
        payment_link_id: str,
    ) -> Optional[Transaction]:
        """Find transaction by Razorpay payment link ID.

        Args:
            payment_link_id: The Razorpay payment link ID (e.g., plink_xxxxx).

        Returns:
            Optional[Transaction]: Found transaction or None.
        """
        if not payment_link_id:
            return None
        return (
            self.db.query(Transaction)
            .filter(Transaction.payment_link_id == payment_link_id)
            .first()
        )

    def mark_transaction_captured(
        self,
        razorpay_payment_id: str,
        razorpay_order_id: Optional[str] = None,
        amount: Optional[int] = None,
        currency: str = "INR",
        payment_method: Optional[str] = None,
        customer_id: Optional[str] = None,
        payment_link_id: Optional[str] = None,
        notes: Optional[Dict[str, Any]] = None,
    ) -> Optional[Transaction]:
        """Acknowledge a captured payment with attribution semantics.

        - If the payment is correlated with a RecoverAI recovery action (e.g., matching
          payment_link_id or recovery notes), transitions status to RECOVERED.
        - Otherwise, acknowledges as organic capture and transitions to CAPTURED.
        - Out-of-order protection: never overwrites a RECOVERED transaction back to CAPTURED.

        Args:
            razorpay_payment_id: Razorpay payment ID.
            razorpay_order_id: Razorpay order ID.
            amount: Transaction amount in subunits.
            currency: Currency code.
            payment_method: Payment method used.
            customer_id: Customer ID.
            payment_link_id: Optional payment link ID for recovery attribution.
            notes: Optional metadata notes from the payment entity.

        Returns:
            Optional[Transaction]: Updated or created transaction.
        """
        txn: Optional[Transaction] = None
        notes_dict = notes if isinstance(notes, dict) else {}

        # 1. Try matching by internal transaction_id from recovery notes
        if "transaction_id" in notes_dict:
            txn = (
                self.db.query(Transaction)
                .filter(Transaction.id == str(notes_dict["transaction_id"]))
                .first()
            )

        # 2. Try matching by payment link ID
        plink = payment_link_id or notes_dict.get("payment_link_id")
        if not txn and plink:
            txn = self.get_transaction_by_payment_link_id(plink)

        # 3. Try matching by payment ID
        if not txn:
            txn = self.get_transaction_by_payment_id(razorpay_payment_id)

        # 4. Try matching by order ID
        if not txn and razorpay_order_id:
            txn = (
                self.db.query(Transaction)
                .filter(Transaction.razorpay_order_id == razorpay_order_id)
                .first()
            )

        if txn:
            # Determine attribution: was this capture caused by RecoverAI?
            is_recovered_by_recoverai = (
                txn.payment_link_id is not None
                or plink is not None
                or notes_dict.get("recovered_by") == "RecoverAI"
            )

            if is_recovered_by_recoverai:
                txn.status = "RECOVERED"
                logger.info(
                    "Transaction %s marked RECOVERED via verified recovery action (link=%s)",
                    txn.id,
                    txn.payment_link_id or plink,
                )
            elif txn.status != "RECOVERED":
                # Organic / unrelated capture
                txn.status = "CAPTURED"
                logger.info("Transaction %s marked CAPTURED (organic capture)", txn.id)

            if customer_id and not txn.customer_id:
                txn.customer_id = customer_id

            self.db.commit()
            self.db.refresh(txn)
            return txn

        # If no prior failed transaction existed, record new payment with CAPTURED status
        if amount is not None:
            txn = Transaction(
                razorpay_payment_id=razorpay_payment_id,
                razorpay_order_id=razorpay_order_id,
                customer_id=customer_id,
                amount=amount,
                currency=currency,
                payment_method=payment_method,
                status="CAPTURED",
            )
            self.db.add(txn)
            self.db.commit()
            self.db.refresh(txn)
            logger.info("Recorded new captured payment %s as CAPTURED", txn.id)
            return txn

        return None

    def mark_transaction_recovered(
        self,
        razorpay_payment_id: str,
        recovery_action: Optional[str] = None,
    ) -> Optional[Transaction]:
        """Mark a transaction as RECOVERED when causality from a RecoverAI recovery action is confirmed.

        Args:
            razorpay_payment_id: Razorpay payment ID.
            recovery_action: The recovery action that produced the recovery.

        Returns:
            Optional[Transaction]: Updated transaction or None.
        """
        txn = self.get_transaction_by_payment_id(razorpay_payment_id)
        if txn:
            txn.status = "RECOVERED"
            self.db.commit()
            self.db.refresh(txn)
            logger.info("Transaction %s marked RECOVERED (action=%s)", txn.id, recovery_action)
            return txn
        return None
