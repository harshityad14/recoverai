"""Pydantic schemas for customer context and history summaries."""

from typing import List, Optional
from pydantic import BaseModel, Field


class CustomerHistorySummary(BaseModel):
    """Aggregated customer payment history and active risk flags."""

    customer_id: Optional[str] = Field(
        default=None,
        description="Customer identifier, or None if anonymous/unspecified",
    )
    total_attempts: int = Field(
        default=0,
        description="Total lifetime payment attempts recorded for this customer",
    )
    attempt_count_24h: int = Field(
        default=0,
        description="Number of payment attempts recorded within the last 24 hours",
    )
    previous_successful_payments: int = Field(
        default=0,
        description="Count of successfully captured or recovered payments",
    )
    previous_recovered_payments: int = Field(
        default=0,
        description="Count of payments specifically recovered by RecoverAI recovery actions",
    )
    previous_failed_payments: int = Field(
        default=0,
        description="Count of previous failed payments for this customer",
    )
    active_risk_flags: List[str] = Field(
        default_factory=list,
        description="List of active risk/fraud flags associated with customer",
    )
