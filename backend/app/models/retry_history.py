"""Retry history database model.

Logs individual recovery attempts executed by RecoverAI for a given transaction.
"""

import uuid
from sqlalchemy import Column, DateTime, Float, ForeignKey, Integer, String, Text, func
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
        doc="Result outcome of attempt (e.g., SUCCESS, FAILED, EXPIRED, PENDING, LINK_CREATED)",
    )
    external_id = Column(
        String(64),
        nullable=True,
        index=True,
        doc="External identifier such as Razorpay payment_link_id",
    )

    # ── Phase 7 End-to-End Audit Trail & Outcome Tracking ──
    recommended_action = Column(
        String(50),
        nullable=True,
        doc="Advisory action recommended by AI decision engine",
    )
    confidence = Column(
        Float,
        nullable=True,
        doc="AI recommendation confidence score (0.0 to 1.0)",
    )
    ai_rationale = Column(
        Text,
        nullable=True,
        doc="Explanation/reasoning provided by AI decision engine",
    )
    safety_decision = Column(
        String(50),
        nullable=True,
        doc="Deterministic verdict from Safety Guard (APPROVE, OVERRIDE, STOP)",
    )
    safety_rule_id = Column(
        String(50),
        nullable=True,
        doc="Identifier of the specific safety rule triggered",
    )
    final_action = Column(
        String(50),
        nullable=True,
        doc="Final action authorized by Safety Guard",
    )
    execution_result = Column(
        String(50),
        nullable=True,
        doc="Result of the executed action (SUCCESS, FAILED, ACTION_NOT_SUPPORTED, etc.)",
    )
    error_code = Column(
        String(50),
        nullable=True,
        doc="Error code if execution failed or was unsupported",
    )
    error_message = Column(
        Text,
        nullable=True,
        doc="Error description if execution failed or was unsupported",
    )
    recovered_amount = Column(
        Integer,
        nullable=True,
        doc="Recovered amount in currency subunits upon verified payment capture",
    )
    recovered_at = Column(
        DateTime(timezone=True),
        nullable=True,
        doc="Timestamp when recovery was verified via payment capture",
    )

    # Relationships
    transaction = relationship("Transaction", back_populates="retry_history")
