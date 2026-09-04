"""Recovery Metrics Service.

Calculates deterministic recovery metrics directly from database state with zero LLM involvement.
Strictly adheres to:
    recovery_rate = total_recovered_transactions / eligible_failed_transactions
    If eligible_failed_transactions == 0: recovery_rate = 0.0
"""

import logging
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.schemas.metrics import RecoveryMetrics
from app.schemas.taxonomy import FailureCategory
from app.schemas.transaction import TransactionStatus

logger = logging.getLogger(__name__)


class RecoveryMetricsService:
    """Service for computing deterministic recovery metrics from database state."""

    def __init__(self, db: Session):
        """Initialize with an active SQLAlchemy database session.

        Args:
            db: SQLAlchemy Session instance.
        """
        self.db = db

    def calculate_metrics(self) -> RecoveryMetrics:
        """Compute all recovery metrics deterministically from database transactions.

        Rules:
        - revenue_at_risk: Sum of amounts for eligible failed/recovery-pending transactions not recovered.
        - recovered_revenue: Sum of amounts for transactions in RECOVERED state.
        - recovery_rate: total_recovered_transactions / eligible_failed_transactions (0.0 if denominator is 0).
        - total_failed_transactions: Count of transactions in FAILED state.
        - total_recovered_transactions: Count of transactions in RECOVERED state.
        - payment_links_created: Count of transactions with payment_link_id created.
        - stopped_transactions: Count of transactions in STOPPED state.

        Returns:
            RecoveryMetrics: Strongly-typed metrics object.
        """
        # 1. Total recovered transactions
        total_recovered = (
            self.db.query(func.count(Transaction.id))
            .filter(Transaction.status == TransactionStatus.RECOVERED.value)
            .scalar()
            or 0
        )

        # 2. Recovered revenue (Sum of amounts for transactions in RECOVERED state)
        recovered_revenue = (
            self.db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(Transaction.status == TransactionStatus.RECOVERED.value)
            .scalar()
            or 0
        )

        # 3. Eligible failed transactions:
        # Transactions that entered recovery pipeline and were eligible
        # (status in FAILED, RECOVERY_PENDING, RECOVERED, STOPPED; amount > 0; failure_category != FRAUD_RISK)
        eligible_failed_count = (
            self.db.query(func.count(Transaction.id))
            .filter(
                Transaction.status.in_([
                    TransactionStatus.FAILED.value,
                    TransactionStatus.RECOVERY_PENDING.value,
                    TransactionStatus.RECOVERED.value,
                    TransactionStatus.STOPPED.value,
                ]),
                Transaction.amount > 0,
                or_(
                    Transaction.failure_category.is_(None),
                    Transaction.failure_category != FailureCategory.FRAUD_RISK.value,
                ),
            )
            .scalar()
            or 0
        )

        # 4. Revenue at risk:
        # Sum of amounts for eligible failed/recovery-pending transactions that have not been recovered
        revenue_at_risk = (
            self.db.query(func.coalesce(func.sum(Transaction.amount), 0))
            .filter(
                Transaction.status.in_([
                    TransactionStatus.FAILED.value,
                    TransactionStatus.RECOVERY_PENDING.value,
                ]),
                Transaction.amount > 0,
                or_(
                    Transaction.failure_category.is_(None),
                    Transaction.failure_category != FailureCategory.FRAUD_RISK.value,
                ),
            )
            .scalar()
            or 0
        )

        # 5. Recovery rate:
        # recovery_rate = total_recovered_transactions / eligible_failed_transactions
        # If eligible_failed_transactions == 0: recovery_rate = 0.0
        if eligible_failed_count > 0:
            recovery_rate = round(float(total_recovered) / float(eligible_failed_count), 4)
        else:
            recovery_rate = 0.0

        # 6. Total failed transactions (currently in FAILED state)
        total_failed = (
            self.db.query(func.count(Transaction.id))
            .filter(Transaction.status == TransactionStatus.FAILED.value)
            .scalar()
            or 0
        )

        # 7. Payment links created
        payment_links_created = (
            self.db.query(func.count(Transaction.id))
            .filter(Transaction.payment_link_id.isnot(None))
            .scalar()
            or 0
        )

        # 8. Stopped transactions
        stopped_transactions = (
            self.db.query(func.count(Transaction.id))
            .filter(Transaction.status == TransactionStatus.STOPPED.value)
            .scalar()
            or 0
        )

        logger.debug(
            "Calculated recovery metrics: recovered_revenue=%d, revenue_at_risk=%d, "
            "rate=%.4f (recovered=%d / eligible=%d)",
            recovered_revenue,
            revenue_at_risk,
            recovery_rate,
            total_recovered,
            eligible_failed_count,
        )

        return RecoveryMetrics(
            revenue_at_risk=int(revenue_at_risk),
            recovered_revenue=int(recovered_revenue),
            recovery_rate=float(recovery_rate),
            total_failed_transactions=int(total_failed),
            total_recovered_transactions=int(total_recovered),
            payment_links_created=int(payment_links_created),
            stopped_transactions=int(stopped_transactions),
            eligible_failed_transactions=int(eligible_failed_count),
        )
