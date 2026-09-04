"""Action Execution Schemas.

Defines the strongly typed data contract for recovery action execution outcomes
produced by the ActionExecutor (Phase 6).
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

from app.services.llm.schemas import RecoveryAction


class ActionResult(BaseModel):
    """Structured result of a recovery action execution attempt.

    Attributes:
        success: Whether the recovery action executed successfully.
        action: The recovery action that was executed.
        transaction_id: Internal RecoverAI transaction record UUID.
        external_id: External identifier when available (e.g., Razorpay payment link ID).
        payment_link_url: Customer-facing short URL for payment links when available.
        error_code: Machine-readable error identifier when execution failed.
        error_message: Sanitized human-readable error description when execution failed.
        timestamp: UTC timestamp when the action execution completed.
        idempotent: Whether this result returned an existing action without re-execution.
        details: Additional sanitized execution metadata (never contains secrets).
    """

    success: bool = Field(
        ...,
        description="Whether the recovery action executed successfully",
    )
    action: RecoveryAction = Field(
        ...,
        description="The recovery action executed or attempted",
    )
    transaction_id: str = Field(
        ...,
        description="Internal RecoverAI transaction record UUID",
    )
    external_id: Optional[str] = Field(
        default=None,
        description="External identifier such as Razorpay payment_link_id (plink_xxxxx)",
    )
    payment_link_url: Optional[str] = Field(
        default=None,
        description="Hosted short URL for the created payment link",
    )
    error_code: Optional[str] = Field(
        default=None,
        description="Error code identifier if execution failed",
    )
    error_message: Optional[str] = Field(
        default=None,
        description="Human-readable error description if execution failed",
    )
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of execution completion",
    )
    idempotent: bool = Field(
        default=False,
        description="True if an existing recovery action was reused without duplicate execution",
    )
    details: Dict[str, Any] = Field(
        default_factory=dict,
        description="Sanitized metadata regarding the execution attempt",
    )
