"""Initial Database Models and Base Declarative Configuration.

Phase 1 establishes the base schema abstractions. Business entities for
PaymentFailureEvent, RecoveryAction, and AuditLog are intentionally deferred
to subsequent phases per buildathon requirements.
"""

from datetime import datetime
from sqlalchemy import Column, DateTime, func
from app.core.database import Base


class TimestampMixin:
    """Mixin for models requiring automatic created_at and updated_at timestamps."""

    created_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
        doc="Timestamp when the record was created",
    )
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        doc="Timestamp when the record was last updated",
    )


# Export Base and TimestampMixin
__all__ = ["Base", "TimestampMixin"]
