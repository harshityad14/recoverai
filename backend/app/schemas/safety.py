"""Safety Decision Schemas and Enums.

Defines the strongly typed data contract for the Deterministic Safety Guard (Phase 5).
The Safety Guard is the authoritative enforcer that evaluates advisory LLM recovery
recommendations against deterministic business rules before any action is permitted.

"LLM recommends. Deterministic safety guard decides."
"""

from enum import Enum
from pydantic import BaseModel, Field

from app.services.llm.schemas import RecoveryAction


class GuardDecision(str, Enum):
    """Safety guard verdicts.

    APPROVE: The recommended action satisfies all safety rules and is authorized.
    OVERRIDE: The recommended action was modified or replaced by a safer alternative.
    STOP: Automated recovery is halted due to terminal state or policy violation.
    """

    APPROVE = "APPROVE"
    OVERRIDE = "OVERRIDE"
    STOP = "STOP"


class SafetyRuleId(str, Enum):
    """Machine-readable rule identifiers for audit logging and dashboards.

    Every SafetyDecision records the exact deterministic rule that governed the outcome.
    """

    ALREADY_CAPTURED = "ALREADY_CAPTURED"
    ALREADY_RECOVERED = "ALREADY_RECOVERED"
    TRANSACTION_STOPPED = "TRANSACTION_STOPPED"
    INVALID_ACTION = "INVALID_ACTION"
    LOW_CONFIDENCE = "LOW_CONFIDENCE"
    RETRY_LIMIT_REACHED = "RETRY_LIMIT_REACHED"
    RETRY_NOT_ELIGIBLE = "RETRY_NOT_ELIGIBLE"
    PAYMENT_LINK_NOT_ELIGIBLE = "PAYMENT_LINK_NOT_ELIGIBLE"
    REMINDER_NOT_ELIGIBLE = "REMINDER_NOT_ELIGIBLE"
    APPROVED = "APPROVED"


class SafetyDecision(BaseModel):
    """Strongly typed decision produced by the Deterministic Safety Guard.

    Attributes:
        decision: Verdict (APPROVE, OVERRIDE, STOP).
        final_action: Final permitted recovery action (RETRY, PAYMENT_LINK, REMINDER, STOP).
        reason: Human-readable explanation of why this decision was reached.
        rule_id: Machine-readable identifier of the governing safety rule.
    """

    decision: GuardDecision = Field(
        ...,
        description="Safety verdict: APPROVE, OVERRIDE, or STOP",
    )
    final_action: RecoveryAction = Field(
        ...,
        description="Final permitted recovery action",
    )
    reason: str = Field(
        ...,
        min_length=1,
        description="Human-readable explanation of the safety decision",
    )
    rule_id: SafetyRuleId = Field(
        ...,
        description="Machine-readable identifier of the governing safety rule",
    )
