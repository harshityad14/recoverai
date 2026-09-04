"""Retry history database model.

Logs individual recovery attempts executed by RecoverAI for a given transaction.
"""

import uuid
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import relationship

from app.models.base import Base


class RetryHistory(Base):
    """Log record of recovery actions and attempts for a transaction."""

    __tablename__ = "retry_history"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="Internal primary key UUID",
    )
    transaction_id = Column(
        String(36),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
        doc="Foreign key reference to transactions.id",
    )
    attempt_number = Column(
        Integer,
        nullable=False,
        doc="Sequential attempt count for this transaction (1, 2, ...)",
    )
    action = Column(
        String(100),
        nullable=False,
        doc="Recovery action taken (e.g., smart_retry, customer_sms_prompt, payment_link)",
    )
    attempted_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when this attempt was initiated",
    )
    result = Column(
        String(50),
        nullable=True,
        doc="Result outcome of attempt (e.g., SUCCESS, FAILED, EXPIRED, PENDING)",
    )
    external_id = Column(
        String(64),
        nullable=True,
        index=True,
        doc="External identifier such as Razorpay payment_link_id",
    )

    # Relationships
    transaction = relationship("Transaction", back_populates="retry_history")
