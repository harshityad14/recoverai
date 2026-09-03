"""Normalized Payment Analysis Pydantic Schema.

Defines the structured output of the Analysis Service passed to downstream
services (e.g. the future LLM Decision Engine).
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class PaymentAnalysis(BaseModel):
    """Normalized payment failure analysis output."""

    transaction_id: str = Field(
        ...,
        description="Internal RecoverAI transaction record UUID",
    )
    razorpay_payment_id: str = Field(
        ...,
        description="Razorpay payment identifier (e.g., pay_xxxxx)",
    )
    razorpay_order_id: Optional[str] = Field(
        default=None,
        description="Razorpay order identifier (e.g., order_xxxxx)",
    )
    customer_id: Optional[str] = Field(
        default=None,
        description="Extracted customer identifier (or None if anonymous)",
    )
    amount: int = Field(
        ...,
        description="Payment amount in subunits (e.g., paise)",
    )
    currency: str = Field(
        default="INR",
        description="Three-letter ISO currency code",
    )
    payment_method: Optional[str] = Field(
        default=None,
        description="Payment method used (e.g., card, upi, netbanking)",
    )
    failure_category: str = Field(
        ...,
        description="Deterministic failure taxonomy classification",
    )
    failure_code: Optional[str] = Field(
        default=None,
        description="Raw error code from Razorpay (e.g., BAD_REQUEST_ERROR)",
    )
    failure_description: Optional[str] = Field(
        default=None,
        description="Human-readable error description from Razorpay",
    )
    attempt_count_24h: int = Field(
        default=0,
        description="Total payment attempts recorded for this customer in the past 24 hours",
    )
    previous_successful_payments: int = Field(
        default=0,
        description="Number of previously successful payments recorded for this customer",
    )
    active_risk_flags: List[str] = Field(
        default_factory=list,
        description="Active risk/fraud flags associated with this customer",
    )
    recovery_context: Dict[str, Any] = Field(
        default_factory=dict,
        description="Recovery eligibility and context for the future LLM decision engine",
    )
