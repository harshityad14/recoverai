"""Deterministic Safety Guard Service.

Hard business rule validation layer that evaluates every LLM recovery recommendation
before any recovery action can execute.

CORE PRINCIPLE:
- Gemini is recommendation-only.
- The Safety Guard is the final authority.
- Gemini must NEVER directly execute Razorpay APIs or recovery actions.
- LLM recommendations are untrusted input.

The Safety Guard is a pure deterministic business-logic layer with zero external
dependencies: it does NOT call Gemini, Razorpay, Redis, or any external network API.

"LLM recommends. Deterministic safety guard decides."
"""

import logging
from typing import Any, Optional, Set, Union

from app.core.config import settings
from app.schemas.analysis import PaymentAnalysis
from app.schemas.customer import CustomerHistorySummary
from app.schemas.safety import GuardDecision, SafetyDecision, SafetyRuleId
from app.schemas.taxonomy import FailureCategory
from app.schemas.transaction import TransactionStatus
from app.services.llm.schemas import RecoveryAction, RecoveryDecision

logger = logging.getLogger(__name__)

# Blocking risk flags that disqualify a transaction from autonomous recovery
BLOCKING_RISK_FLAGS: Set[str] = {
    "FRAUD_SUSPICION",
    "BLACKLISTED",
    "CHARGEBACK_HISTORY",
    "HIGH_RISK_CUSTOMER",
    "SECURITY_VIOLATION",
}

# Failure categories classified as transient (eligible for retry)
TRANSIENT_FAILURE_CATEGORIES: Set[str] = {
    FailureCategory.BANK_TIMEOUT.value,
    FailureCategory.NETWORK_ERROR.value,
    FailureCategory.PAYMENT_TIMEOUT.value,
}


class SafetyGuard:
    """Deterministic Safety Guard evaluating advisory recovery recommendations.

    Enforces hard business rules, retry caps, state machine boundaries,
    failure taxonomy eligibility, and confidence thresholds.
    """

    def __init__(
        self,
        min_confidence: Optional[float] = None,
        max_retries: Optional[int] = None,
    ):
        """Initialize SafetyGuard with configurable thresholds.

        Args:
            min_confidence: Minimum LLM confidence required to accept a recommendation.
                            Defaults to settings.LLM_MIN_CONFIDENCE (0.70).
            max_retries: Maximum permitted recovery retries for a single transaction.
                         Defaults to settings.MAX_RECOVERY_RETRIES (2).
        """
        self.min_confidence: float = (
            min_confidence
            if min_confidence is not None
            else settings.LLM_MIN_CONFIDENCE
        )
        self.max_retries: int = (
            max_retries
            if max_retries is not None
            else settings.MAX_RECOVERY_RETRIES
        )

    def evaluate(
        self,
        transaction_status: Union[TransactionStatus, str, Any],
        analysis: PaymentAnalysis,
        customer_history: Optional[CustomerHistorySummary] = None,
        recovery_decision: Optional[RecoveryDecision] = None,
        retry_attempts: Optional[int] = None,
    ) -> SafetyDecision:
        """Evaluate an advisory recovery recommendation against deterministic safety rules.

        Rules are evaluated in strict order of priority:
        1. Already CAPTURED / RECOVERED
        2. Already STOPPED
        3. Invalid decision / unknown action
        4. STOP recommendation
        5. Confidence threshold
        6. Retry attempt limit
        7. Action eligibility
        8. APPROVE

        Args:
            transaction_status: Current lifecycle state of the transaction.
            analysis: Normalized payment failure analysis from Phase 3.
            customer_history: Aggregated customer history and risk flags.
            recovery_decision: Advisory recommendation from LLM Decision Engine.
            retry_attempts: Number of recovery retries already attempted for this transaction.

        Returns:
            SafetyDecision: Authoritative deterministic verdict and permitted action.
        """
        # Normalize transaction status string
        if hasattr(transaction_status, "status"):
            status_str = str(transaction_status.status).upper()
        elif isinstance(transaction_status, TransactionStatus):
            status_str = transaction_status.value
        else:
            status_str = str(transaction_status).upper()

        # Normalize retry attempts count
        if retry_attempts is not None:
            attempts = int(retry_attempts)
        elif hasattr(transaction_status, "retry_history") and transaction_status.retry_history is not None:
            attempts = len(transaction_status.retry_history)
        elif analysis.recovery_context and "retry_attempts" in analysis.recovery_context:
            attempts = int(analysis.recovery_context["retry_attempts"])
        else:
            attempts = 0

        payment_ref = getattr(analysis, "razorpay_payment_id", "unknown")

        # ------------------------------------------------------------------
        # PRIORITY 1: Already CAPTURED or RECOVERED (Prevent duplicate recovery)
        # ------------------------------------------------------------------
        if status_str == TransactionStatus.CAPTURED.value:
            logger.info("Payment %s is already CAPTURED; halting recovery", payment_ref)
            return SafetyDecision(
                decision=GuardDecision.STOP,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.ALREADY_CAPTURED,
                reason="Transaction is already CAPTURED; no further recovery action permitted.",
            )

        if status_str == TransactionStatus.RECOVERED.value:
            logger.info("Payment %s is already RECOVERED; halting recovery", payment_ref)
            return SafetyDecision(
                decision=GuardDecision.STOP,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.ALREADY_RECOVERED,
                reason="Transaction is already RECOVERED; no further recovery action permitted.",
            )

        # ------------------------------------------------------------------
        # PRIORITY 2: Already STOPPED (Terminal lifecycle state)
        # ------------------------------------------------------------------
        if status_str == TransactionStatus.STOPPED.value:
            logger.info("Payment %s is already STOPPED; halting recovery", payment_ref)
            return SafetyDecision(
                decision=GuardDecision.STOP,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.TRANSACTION_STOPPED,
                reason="Transaction is in STOPPED state; no further recovery action permitted.",
            )

        # ------------------------------------------------------------------
        # PRIORITY 3: Invalid decision or unknown action (Fail closed)
        # ------------------------------------------------------------------
        if recovery_decision is None:
            logger.warning("Payment %s received None recovery_decision; failing closed to STOP", payment_ref)
            return SafetyDecision(
                decision=GuardDecision.OVERRIDE,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.INVALID_ACTION,
                reason="No recovery decision provided; failing closed to STOP.",
            )

        raw_action = getattr(recovery_decision, "action", None)
        action: Optional[RecoveryAction] = None
        if isinstance(raw_action, RecoveryAction):
            action = raw_action
        elif isinstance(raw_action, str):
            try:
                action = RecoveryAction(raw_action)
            except (ValueError, KeyError):
                action = None

        if action is None:
            logger.warning(
                "Payment %s received invalid action '%s'; failing closed to STOP",
                payment_ref,
                raw_action,
            )
            return SafetyDecision(
                decision=GuardDecision.OVERRIDE,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.INVALID_ACTION,
                reason=f"Invalid or unrecognized recovery action '{raw_action}'; failing closed to STOP.",
            )

        # ------------------------------------------------------------------
        # PRIORITY 4: STOP recommendation (RULE 1: STOP must always remain STOP)
        # ------------------------------------------------------------------
        if action == RecoveryAction.STOP:
            logger.info("Payment %s LLM recommended STOP; approved", payment_ref)
            return SafetyDecision(
                decision=GuardDecision.APPROVE,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.APPROVED,
                reason="LLM recommended STOP; approved with no further recovery action.",
            )

        # ------------------------------------------------------------------
        # PRIORITY 5: Confidence threshold (RULE 3: Low confidence fails to STOP)
        # ------------------------------------------------------------------
        confidence = getattr(recovery_decision, "confidence", 0.0)
        try:
            confidence_val = float(confidence)
        except (TypeError, ValueError):
            confidence_val = 0.0

        if confidence_val < self.min_confidence:
            logger.info(
                "Payment %s confidence %.2f below threshold %.2f; overriding to STOP",
                payment_ref,
                confidence_val,
                self.min_confidence,
            )
            return SafetyDecision(
                decision=GuardDecision.OVERRIDE,
                final_action=RecoveryAction.STOP,
                rule_id=SafetyRuleId.LOW_CONFIDENCE,
                reason=(
                    f"LLM confidence {confidence_val:.2f} is below the minimum "
                    f"required confidence of {self.min_confidence:.2f}."
                ),
            )

        # ------------------------------------------------------------------
        # PRIORITY 6: Retry attempt limit (RULE 4: Maximum recovery retries)
        # ------------------------------------------------------------------
        if action == RecoveryAction.RETRY:
            if attempts >= self.max_retries:
                if self._is_payment_link_eligible(analysis, customer_history):
                    logger.info(
                        "Payment %s reached retry limit (%d/%d); overriding to PAYMENT_LINK",
                        payment_ref,
                        attempts,
                        self.max_retries,
                    )
                    return SafetyDecision(
                        decision=GuardDecision.OVERRIDE,
                        final_action=RecoveryAction.PAYMENT_LINK,
                        rule_id=SafetyRuleId.RETRY_LIMIT_REACHED,
                        reason=(
                            f"Transaction has reached maximum retry attempts "
                            f"({attempts}/{self.max_retries}); falling back to eligible PAYMENT_LINK."
                        ),
                    )

                logger.info(
                    "Payment %s reached retry limit (%d/%d); payment link ineligible, overriding to STOP",
                    payment_ref,
                    attempts,
                    self.max_retries,
                )
                return SafetyDecision(
                    decision=GuardDecision.OVERRIDE,
                    final_action=RecoveryAction.STOP,
                    rule_id=SafetyRuleId.RETRY_LIMIT_REACHED,
                    reason=(
                        f"Transaction has reached maximum retry attempts "
                        f"({attempts}/{self.max_retries}); payment link is ineligible, stopping recovery."
                    ),
                )

        # ------------------------------------------------------------------
        # PRIORITY 7: Action eligibility
        # ------------------------------------------------------------------
        # RULE 7: RETRY eligibility
        if action == RecoveryAction.RETRY:
            if not self._is_retry_eligible(analysis, customer_history):
                if self._is_payment_link_eligible(analysis, customer_history):
                    logger.info(
                        "Payment %s ineligible for RETRY; overriding to PAYMENT_LINK",
                        payment_ref,
                    )
                    return SafetyDecision(
                        decision=GuardDecision.OVERRIDE,
                        final_action=RecoveryAction.PAYMENT_LINK,
                        rule_id=SafetyRuleId.RETRY_NOT_ELIGIBLE,
                        reason="Transaction is not eligible for RETRY; falling back to eligible PAYMENT_LINK.",
                    )

                logger.info(
                    "Payment %s ineligible for RETRY and PAYMENT_LINK; overriding to STOP",
                    payment_ref,
                )
                return SafetyDecision(
                    decision=GuardDecision.OVERRIDE,
                    final_action=RecoveryAction.STOP,
                    rule_id=SafetyRuleId.RETRY_NOT_ELIGIBLE,
                    reason="Transaction is not eligible for RETRY and fallback PAYMENT_LINK is ineligible; stopping recovery.",
                )

        # RULE 8: PAYMENT_LINK eligibility
        elif action == RecoveryAction.PAYMENT_LINK:
            if not self._is_payment_link_eligible(analysis, customer_history):
                logger.info(
                    "Payment %s ineligible for PAYMENT_LINK; overriding to STOP",
                    payment_ref,
                )
                return SafetyDecision(
                    decision=GuardDecision.OVERRIDE,
                    final_action=RecoveryAction.STOP,
                    rule_id=SafetyRuleId.PAYMENT_LINK_NOT_ELIGIBLE,
                    reason="Transaction is not eligible for PAYMENT_LINK recovery; stopping recovery.",
                )

        # RULE 9: REMINDER eligibility
        elif action == RecoveryAction.REMINDER:
            if not self._is_reminder_eligible(analysis, customer_history):
                logger.info(
                    "Payment %s context ineligible or missing for REMINDER; overriding to STOP",
                    payment_ref,
                )
                return SafetyDecision(
                    decision=GuardDecision.OVERRIDE,
                    final_action=RecoveryAction.STOP,
                    rule_id=SafetyRuleId.REMINDER_NOT_ELIGIBLE,
                    reason="Required customer or transaction context for REMINDER is unavailable or ineligible; stopping recovery.",
                )

        # ------------------------------------------------------------------
        # PRIORITY 8: APPROVE
        # ------------------------------------------------------------------
        logger.info(
            "Payment %s recommendation %s satisfied all safety rules; APPROVED",
            payment_ref,
            action.value,
        )
        return SafetyDecision(
            decision=GuardDecision.APPROVE,
            final_action=action,
            rule_id=SafetyRuleId.APPROVED,
            reason=f"Recommended action {action.value} satisfies all deterministic safety criteria and is approved.",
        )

    # ----------------------------------------------------------------------
    # Deterministic Eligibility Helpers (Pure business logic)
    # ----------------------------------------------------------------------

    @staticmethod
    def _has_blocking_risk(
        analysis: PaymentAnalysis,
        customer_history: Optional[CustomerHistorySummary],
    ) -> bool:
        """Check whether transaction or customer has active blocking risk flags."""
        analysis_flags = set(getattr(analysis, "active_risk_flags", []) or [])
        if analysis_flags.intersection(BLOCKING_RISK_FLAGS):
            return True

        if customer_history and customer_history.active_risk_flags:
            history_flags = set(customer_history.active_risk_flags)
            if history_flags.intersection(BLOCKING_RISK_FLAGS):
                return True

        return False

    def _is_retry_eligible(
        self,
        analysis: PaymentAnalysis,
        customer_history: Optional[CustomerHistorySummary],
    ) -> bool:
        """Determine whether the payment failure is eligible for automated RETRY."""
        # Must have positive amount
        if analysis.amount <= 0:
            return False

        # Fraud classification disqualifies from all automated recovery
        if analysis.failure_category == FailureCategory.FRAUD_RISK.value:
            return False

        # Active blocking risk flags prevent automated retry
        if self._has_blocking_risk(analysis, customer_history):
            return False

        # Explicitly marked ineligible in recovery context
        if analysis.recovery_context and analysis.recovery_context.get("eligible_for_analysis") is False:
            return False

        # Transient failure check: only transient categories are eligible for automated retry
        is_transient = (
            analysis.recovery_context.get("is_transient_failure", False)
            if analysis.recovery_context
            else False
        )
        if not is_transient and analysis.failure_category not in TRANSIENT_FAILURE_CATEGORIES:
            return False

        return True

    def _is_payment_link_eligible(
        self,
        analysis: PaymentAnalysis,
        customer_history: Optional[CustomerHistorySummary],
    ) -> bool:
        """Determine whether the payment failure is eligible for PAYMENT_LINK recovery."""
        # Must have positive amount
        if analysis.amount <= 0:
            return False

        # Fraud classification disqualifies from payment link
        if analysis.failure_category == FailureCategory.FRAUD_RISK.value:
            return False

        # Active blocking risk flags prevent payment links
        if self._has_blocking_risk(analysis, customer_history):
            return False

        # Explicitly marked ineligible for analysis
        if analysis.recovery_context and analysis.recovery_context.get("eligible_for_analysis") is False:
            return False

        return True

    def _is_reminder_eligible(
        self,
        analysis: PaymentAnalysis,
        customer_history: Optional[CustomerHistorySummary],
    ) -> bool:
        """Determine whether the transaction has sufficient context for REMINDER."""
        # Customer ID must be known and non-empty
        cust_id = getattr(analysis, "customer_id", None)
        if not cust_id or not str(cust_id).strip() or str(cust_id).lower() in ("anonymous", "none"):
            return False

        # Must have positive amount
        if analysis.amount <= 0:
            return False

        # Fraud classification disqualifies from reminder
        if analysis.failure_category == FailureCategory.FRAUD_RISK.value:
            return False

        # Active blocking risk flags prevent customer reminder
        if self._has_blocking_risk(analysis, customer_history):
            return False

        # Explicitly marked ineligible for analysis
        if analysis.recovery_context and analysis.recovery_context.get("eligible_for_analysis") is False:
            return False

        return True
