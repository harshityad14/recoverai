"""Risk flags database model.

Stores fraud/risk flags associated with customer profiles to prevent risky recoveries.
"""

import uuid
from sqlalchemy import Boolean, Column, DateTime, String, func

from app.models.base import Base


class RiskFlag(Base):
    """Customer-level risk or fraud flag."""

    __tablename__ = "risk_flags"

    id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        doc="Internal primary key UUID",
    )
    customer_id = Column(
        String(64),
        nullable=False,
        index=True,
        doc="Customer identifier to which the flag applies",
    )
    flag = Column(
        String(100),
        nullable=False,
        doc="Risk indicator tag (e.g., FRAUD_SUSPICION, CHARGEBACK_HISTORY, VELOCITY_EXCEEDED)",
    )
    active = Column(
        Boolean,
        default=True,
        nullable=False,
        doc="Whether this flag is currently active and enforceable",
    )
    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when this risk flag was recorded",
    )
