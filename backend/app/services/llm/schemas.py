"""LLM Decision Schemas.

Defines the strongly typed data contract for the LLM Decision Engine output.
All values are advisory recommendations — Phase 5 Safety Guard is the
authoritative enforcer.

"LLM recommends. Deterministic safety guard decides."
"""

from enum import Enum
from pydantic import BaseModel, Field


class RecoveryAction(str, Enum):
    """Allowed recovery action recommendations.

    These are RECOMMENDATIONS, not permissions or authorizations.
    Phase 5 (Deterministic Safety Guard) independently decides whether
    the recommended action is allowed, blocked, or overridden.
    """

    RETRY = "RETRY"
    PAYMENT_LINK = "PAYMENT_LINK"
    REMINDER = "REMINDER"
    STOP = "STOP"


class RecoveryDecision(BaseModel):
    """Validated LLM decision output.

    This is an advisory recommendation produced by the Decision Engine.
    It does NOT authorize execution — Phase 5 Safety Guard independently
    validates, overrides, or blocks the recommendation before any action
    is taken.

    Attributes:
        action: One of RETRY, PAYMENT_LINK, REMINDER, or STOP.
        confidence: LLM's self-assessed confidence in the recommendation
                    (0.0–1.0). This is NOT an authorization signal.
        rationale: Short explanation for the recommendation.
    """

    action: RecoveryAction = Field(
        ...,
        description="Recommended recovery action (advisory only)",
    )
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="LLM self-assessed confidence (0.0–1.0). Not an authorization signal.",
    )
    rationale: str = Field(
        ...,
        min_length=1,
        description="Short explanation for the recommendation",
    )


def create_fallback_decision(reason: str = "LLM decision unavailable; recovery requires deterministic safety handling.") -> RecoveryDecision:
    """Create a safe fallback recommendation.

    Used when the LLM provider times out, fails, returns malformed JSON,
    or produces invalid output. This is a safe RECOMMENDATION fallback,
    not a safety enforcement decision. Phase 5 will still independently
    evaluate the situation.

    Args:
        reason: Human-readable explanation for why the fallback was triggered.

    Returns:
        RecoveryDecision with action=STOP and confidence=0.0.
    """
    return RecoveryDecision(
        action=RecoveryAction.STOP,
        confidence=0.0,
        rationale=reason,
    )
