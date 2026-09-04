"""Transaction database model.

Represents payment transactions tracked by RecoverAI, including failure states
and recovery lifecycle progression.
"""

import uuid
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base, TimestampMixin


class Transaction(Base, TimestampMixin):
    """Payment transaction record for tracking failure analysis and recovery."""

    __tablename__ = "transactions"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="Internal primary key UUID",
    )
    razorpay_payment_id = Column(
        String(64),
        nullable=False,
        unique=True,
        index=True,
        doc="Razorpay payment identifier (e.g., pay_xxxxx)",
    )
    razorpay_order_id = Column(
        String(64),
        nullable=True,
        index=True,
        doc="Razorpay order identifier (e.g., order_xxxxx)",
    )
    customer_id = Column(
        String(64),
        nullable=True,
        index=True,
        doc="Customer identifier from merchant or Razorpay",
    )
    amount = Column(
        Integer,
        nullable=False,
        doc="Transaction amount in smallest currency unit (e.g., paise)",
    )
    currency = Column(
        String(10),
        nullable=False,
        default="INR",
        doc="Three-letter ISO currency code",
    )
    payment_method = Column(
        String(50),
        nullable=True,
        doc="Payment method used (e.g., card, upi, netbanking)",
    )
    status = Column(
        String(50),
        nullable=False,
        default="FAILED",
        doc="Current recovery status (FAILED, RECOVERY_PENDING, CAPTURED, RECOVERED, STOPPED)",
    )
    failure_category = Column(
        String(50),
        nullable=True,
        doc="Domain taxonomy failure category (e.g., BANK_TIMEOUT, INSUFFICIENT_FUNDS)",
    )
    failure_code = Column(
        String(100),
        nullable=True,
        doc="Raw error code from Razorpay (e.g., BAD_REQUEST_ERROR)",
    )
    failure_description = Column(
        Text,
        nullable=True,
        doc="Human-readable error explanation from Razorpay",
    )
    payment_link_id = Column(
        String(64),
        nullable=True,
        index=True,
        doc="Razorpay payment link identifier (e.g., plink_xxxxx)",
    )
    payment_link_url = Column(
        String(255),
        nullable=True,
        doc="Hosted short URL for customer recovery payment link",
    )
    payment_link_reference_id = Column(
        String(64),
        nullable=True,
        index=True,
        doc="Merchant reference identifier for payment link idempotency",
    )

    # Relationships
    retry_history = relationship(
        "RetryHistory",
        back_populates="transaction",
        cascade="all, delete-orphan",
        order_by="RetryHistory.attempt_number",
    )
