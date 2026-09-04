"""Recovery Metrics Schemas.

Defines Pydantic models for deterministic, database-derived recovery metrics.
"""

from pydantic import BaseModel, ConfigDict, Field


class RecoveryMetrics(BaseModel):
    """Deterministic recovery metrics aggregated directly from database state."""

    model_config = ConfigDict(extra="forbid")

    revenue_at_risk: int = Field(
        ...,
        description="Sum of amounts (paise) for eligible failed/recovery-pending transactions that have not been recovered",
        ge=0,
    )
    recovered_revenue: int = Field(
        ...,
        description="Sum of amounts (paise) for transactions in RECOVERED state",
        ge=0,
    )
    recovery_rate: float = Field(
        ...,
        description="Ratio of total_recovered_transactions to eligible_failed_transactions (0.0 when denominator is 0)",
        ge=0.0,
        le=1.0,
    )
    total_failed_transactions: int = Field(
        ...,
        description="Total count of transactions currently in FAILED status",
        ge=0,
    )
    total_recovered_transactions: int = Field(
        ...,
        description="Total count of transactions in RECOVERED status",
        ge=0,
    )
    payment_links_created: int = Field(
        ...,
        description="Total count of transactions with created payment links",
        ge=0,
    )
    stopped_transactions: int = Field(
        ...,
        description="Total count of transactions in STOPPED status",
        ge=0,
    )
    eligible_failed_transactions: int = Field(
        default=0,
        description="Total count of failed transactions eligible for recovery",
        ge=0,
    )
