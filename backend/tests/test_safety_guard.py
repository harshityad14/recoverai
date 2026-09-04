"""Phase 5 — Deterministic Safety Guard Tests.

Verifies the hard business rule validation layer that evaluates every LLM recovery recommendation
before any recovery action can execute.

CORE PRINCIPLE:
- Gemini is recommendation-only.
- The Safety Guard is the final authority.
- Gemini must NEVER directly execute Razorpay APIs or recovery actions.
- LLM recommendations are untrusted input.
- Pure deterministic business-logic layer with ZERO external API calls.

"LLM recommends. Deterministic safety guard decides."
"""

import sys
from typing import Any, Dict, List, Optional
import pytest

from app.core.config import settings
from app.models.transaction import Transaction
from app.schemas.analysis import PaymentAnalysis
from app.schemas.customer import CustomerHistorySummary
from app.schemas.safety import GuardDecision, SafetyDecision, SafetyRuleId
from app.schemas.taxonomy import FailureCategory
from app.schemas.transaction import TransactionStatus
from app.services.llm.schemas import RecoveryAction, RecoveryDecision
from app.services.safety_guard import SafetyGuard


# ---------------------------------------------------------------------------
# Test Helpers & Fixtures
# ---------------------------------------------------------------------------


def _make_analysis(
    payment_id: str = "pay_Test001",
    amount: int = 50000,
    currency: str = "INR",
    payment_method: str = "card",
    failure_category: str = "NETWORK_ERROR",
    failure_code: str = "GATEWAY_ERROR",
    failure_description: str = "Network error during payment processing",
    attempt_count_24h: int = 1,
    previous_successful_payments: int = 3,
    active_risk_flags: Optional[List[str]] = None,
    eligible_for_analysis: bool = True,
    is_transient_failure: bool = True,
    customer_id: Optional[str] = "cust_Test001",
    recovery_context: Optional[Dict[str, Any]] = None,
) -> PaymentAnalysis:
    """Create a test PaymentAnalysis with sensible defaults."""
    ctx = {
        "eligible_for_analysis": eligible_for_analysis,
        "is_transient_failure": is_transient_failure,
        "is_already_captured": False,
        "is_already_recovered": False,
        "requires_step_up_auth": False,
    }
    if recovery_context:
        ctx.update(recovery_context)

    return PaymentAnalysis(
        transaction_id="txn-test-uuid-001",
        razorpay_payment_id=payment_id,
        razorpay_order_id="order_Test001",
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        payment_method=payment_method,
        failure_category=failure_category,
        failure_code=failure_code,
        failure_description=failure_description,
        attempt_count_24h=attempt_count_24h,
        previous_successful_payments=previous_successful_payments,
        active_risk_flags=active_risk_flags or [],
        recovery_context=ctx,
    )


def _make_customer_history(
    customer_id: Optional[str] = "cust_Test001",
    total_attempts: int = 2,
    attempt_count_24h: int = 1,
    previous_successful_payments: int = 3,
    active_risk_flags: Optional[List[str]] = None,
) -> CustomerHistorySummary:
    """Create a test CustomerHistorySummary."""
    return CustomerHistorySummary(
        customer_id=customer_id,
        total_attempts=total_attempts,
        attempt_count_24h=attempt_count_24h,
        previous_successful_payments=previous_successful_payments,
        active_risk_flags=active_risk_flags or [],
    )


def _make_decision(
    action: RecoveryAction = RecoveryAction.RETRY,
    confidence: float = 0.85,
    rationale: str = "Test rationale",
) -> RecoveryDecision:
    """Create a test RecoveryDecision."""
    return RecoveryDecision(
        action=action,
        confidence=confidence,
        rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Test Cases 1–15 (Specification Requirements)
# ---------------------------------------------------------------------------


class TestSafetyGuardCoreRules:
    """Test suite for core deterministic safety rules (Rules 1–9 and Priorities 1–8)."""

    def test_1_stop_recommendation_remains_stop(self):
        """RULE 1: STOP recommendation must always remain STOP (approved, never mutated)."""
        guard = SafetyGuard()
        analysis = _make_analysis()
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.STOP, confidence=0.95, rationale="Risk detected")

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )

        assert result.decision == GuardDecision.APPROVE
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.APPROVED
        assert len(result.reason) > 0

    def test_2_high_confidence_eligible_retry_is_approved(self):
        """Test 2: High-confidence eligible RETRY on transient error is approved."""
        guard = SafetyGuard()
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.88)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
            retry_attempts=0,
        )

        assert result.decision == GuardDecision.APPROVE
        assert result.final_action == RecoveryAction.RETRY
        assert result.rule_id == SafetyRuleId.APPROVED
        assert "approved" in result.reason.lower()

    def test_3_low_confidence_retry_becomes_stop(self):
        """RULE 3: Confidence below configured threshold (0.70) is overridden to STOP."""
        guard = SafetyGuard(min_confidence=0.70)
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.54)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
            retry_attempts=0,
        )

        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.LOW_CONFIDENCE
        assert "0.54" in result.reason
        assert "0.70" in result.reason

    def test_4_retry_limit_prevents_retry(self):
        """RULE 4: Exceeding MAX_RECOVERY_RETRIES prevents RETRY; stops when payment link ineligible."""
        guard = SafetyGuard(max_retries=2)
        # Transaction with negative amount or marked ineligible for analysis
        analysis = _make_analysis(
            failure_category="NETWORK_ERROR",
            is_transient_failure=True,
            eligible_for_analysis=False,
            amount=0,
        )
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.90)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
            retry_attempts=2,
        )

        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.RETRY_LIMIT_REACHED
        assert "2/2" in result.reason

    def test_5_retry_limit_falls_back_to_payment_link_when_eligible(self):
        """RULE 4: Exceeding MAX_RECOVERY_RETRIES falls back to PAYMENT_LINK when eligible."""
        guard = SafetyGuard(max_retries=2)
        analysis = _make_analysis(
            failure_category="NETWORK_ERROR",
            is_transient_failure=True,
            eligible_for_analysis=True,
            amount=50000,
        )
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.90)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
            retry_attempts=2,
        )

        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.PAYMENT_LINK
        assert result.rule_id == SafetyRuleId.RETRY_LIMIT_REACHED
        assert "PAYMENT_LINK" in result.reason

    def test_6_already_captured_prevents_recovery(self):
        """RULE 5 & PRIORITY 1: Already CAPTURED status halts recovery regardless of recommendation."""
        guard = SafetyGuard()
        analysis = _make_analysis()
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.99)

        result = guard.evaluate(
            transaction_status=TransactionStatus.CAPTURED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )

        assert result.decision == GuardDecision.STOP
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.ALREADY_CAPTURED
        assert "CAPTURED" in result.reason

    def test_7_already_recovered_prevents_recovery(self):
        """RULE 5 & PRIORITY 1: Already RECOVERED status halts recovery to prevent duplicate action."""
        guard = SafetyGuard()
        analysis = _make_analysis()
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.PAYMENT_LINK, confidence=0.95)

        result = guard.evaluate(
            transaction_status=TransactionStatus.RECOVERED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )

        assert result.decision == GuardDecision.STOP
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.ALREADY_RECOVERED
        assert "RECOVERED" in result.reason

    def test_8_stopped_transaction_prevents_recovery(self):
        """RULE 6 & PRIORITY 2: STOPPED transaction status halts recovery."""
        guard = SafetyGuard()
        analysis = _make_analysis()
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.90)

        result = guard.evaluate(
            transaction_status=TransactionStatus.STOPPED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )

        assert result.decision == GuardDecision.STOP
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.TRANSACTION_STOPPED
        assert "STOPPED" in result.reason

    def test_9_invalid_action_fails_closed(self):
        """RULE 2 & PRIORITY 3: Invalid or missing action fails closed to STOP with OVERRIDE."""
        guard = SafetyGuard()
        analysis = _make_analysis()
        history = _make_customer_history()

        # Case 9a: None recovery decision
        result_none = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=None,
        )
        assert result_none.decision == GuardDecision.OVERRIDE
        assert result_none.final_action == RecoveryAction.STOP
        assert result_none.rule_id == SafetyRuleId.INVALID_ACTION

        # Case 9b: Mock object with invalid action string
        class MockInvalidDecision:
            action = "INVALID_UNRECOGNIZED_ACTION"
            confidence = 0.90
            rationale = "Bogus action"

        result_invalid = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=MockInvalidDecision(),  # type: ignore
        )
        assert result_invalid.decision == GuardDecision.OVERRIDE
        assert result_invalid.final_action == RecoveryAction.STOP
        assert result_invalid.rule_id == SafetyRuleId.INVALID_ACTION

    def test_10_ineligible_retry_cannot_execute(self):
        """RULE 7: Non-transient failure taxonomy (e.g. CARD_DECLINED) cannot RETRY."""
        guard = SafetyGuard()
        # Card declined: eligible for PAYMENT_LINK, but NOT eligible for automated RETRY
        analysis = _make_analysis(
            failure_category="CARD_DECLINED",
            is_transient_failure=False,
            eligible_for_analysis=True,
        )
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
            retry_attempts=0,
        )

        # Must NOT approve RETRY — must fall back to PAYMENT_LINK
        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.PAYMENT_LINK
        assert result.rule_id == SafetyRuleId.RETRY_NOT_ELIGIBLE

        # Now test when fraud risk makes both RETRY and PAYMENT_LINK ineligible
        fraud_analysis = _make_analysis(
            failure_category="FRAUD_RISK",
            is_transient_failure=False,
            eligible_for_analysis=False,
        )
        result_fraud = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=fraud_analysis,
            customer_history=history,
            recovery_decision=rec,
        )
        assert result_fraud.decision == GuardDecision.OVERRIDE
        assert result_fraud.final_action == RecoveryAction.STOP
        assert result_fraud.rule_id == SafetyRuleId.RETRY_NOT_ELIGIBLE

    def test_11_ineligible_payment_link_cannot_execute(self):
        """RULE 8: Customer with active blocking risk flags or fraud cannot receive PAYMENT_LINK."""
        guard = SafetyGuard()
        analysis = _make_analysis(
            failure_category="INSUFFICIENT_FUNDS",
            active_risk_flags=["BLACKLISTED"],
            eligible_for_analysis=False,
        )
        history = _make_customer_history(active_risk_flags=["BLACKLISTED"])
        rec = _make_decision(action=RecoveryAction.PAYMENT_LINK, confidence=0.85)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )

        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.PAYMENT_LINK_NOT_ELIGIBLE

    def test_12_missing_required_reminder_context_fails_closed(self):
        """RULE 9: Anonymous customer without customer context fails closed to STOP."""
        guard = SafetyGuard()
        # Customer ID is None / empty
        analysis = _make_analysis(
            failure_category="PAYMENT_TIMEOUT",
            customer_id=None,
        )
        rec = _make_decision(action=RecoveryAction.REMINDER, confidence=0.80)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=None,
            recovery_decision=rec,
        )

        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.REMINDER_NOT_ELIGIBLE
        assert "REMINDER" in result.reason

    def test_13_safety_guard_never_calls_gemini(self, monkeypatch: pytest.MonkeyPatch):
        """Test 13: SafetyGuard has zero Gemini/LLM dependencies and never invokes LLM APIs."""
        # Check module imports: app.services.safety_guard must not import google.genai or decision_engine
        import app.services.safety_guard as sg_module
        module_dict = vars(sg_module)
        assert "google" not in module_dict
        assert "DecisionEngine" not in module_dict
        assert "GeminiLLMClient" not in module_dict

        # Verify evaluation executes without calling any LLM
        guard = SafetyGuard()
        analysis = _make_analysis()
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )
        assert result.decision == GuardDecision.APPROVE

    def test_14_safety_guard_never_calls_razorpay(self):
        """Test 14: SafetyGuard has zero Razorpay SDK dependencies and never invokes Razorpay APIs."""
        import app.services.safety_guard as sg_module
        module_dict = vars(sg_module)
        assert "razorpay" not in module_dict
        assert "RazorpayClient" not in module_dict

        guard = SafetyGuard()
        analysis = _make_analysis(failure_category="CARD_DECLINED", is_transient_failure=False)
        rec = _make_decision(action=RecoveryAction.PAYMENT_LINK, confidence=0.80)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
        )
        assert result.decision == GuardDecision.APPROVE
        assert result.final_action == RecoveryAction.PAYMENT_LINK

    def test_15_deterministic_repeated_evaluation_returns_identical_result(self):
        """Test 15: 100 repeated evaluations with identical inputs yield strictly identical outputs."""
        guard = SafetyGuard()
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        history = _make_customer_history()
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)

        first_result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
            retry_attempts=1,
        )

        for _ in range(100):
            repeated = guard.evaluate(
                transaction_status=TransactionStatus.FAILED,
                analysis=analysis,
                customer_history=history,
                recovery_decision=rec,
                retry_attempts=1,
            )
            assert repeated.decision == first_result.decision
            assert repeated.final_action == first_result.final_action
            assert repeated.rule_id == first_result.rule_id
            assert repeated.reason == first_result.reason


# ---------------------------------------------------------------------------
# Boundary & Threshold Tests
# ---------------------------------------------------------------------------


class TestSafetyGuardBoundaries:
    """Boundary conditions for confidence thresholds, retry attempt counts, and status types."""

    def test_confidence_exactly_at_threshold(self):
        """Confidence exactly at 0.70 passes the confidence threshold check."""
        guard = SafetyGuard(min_confidence=0.70)
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.70)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
            retry_attempts=0,
        )
        assert result.decision == GuardDecision.APPROVE
        assert result.final_action == RecoveryAction.RETRY
        assert result.rule_id == SafetyRuleId.APPROVED

    def test_confidence_just_below_threshold(self):
        """Confidence at 0.699 (< 0.70) fails closed with LOW_CONFIDENCE."""
        guard = SafetyGuard(min_confidence=0.70)
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.699)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
            retry_attempts=0,
        )
        assert result.decision == GuardDecision.OVERRIDE
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.LOW_CONFIDENCE

    def test_retry_attempts_exactly_at_max(self):
        """Retry attempts == MAX_RECOVERY_RETRIES (2) triggers RETRY_LIMIT_REACHED."""
        guard = SafetyGuard(max_retries=2)
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
            retry_attempts=2,
        )
        assert result.rule_id == SafetyRuleId.RETRY_LIMIT_REACHED
        assert result.final_action == RecoveryAction.PAYMENT_LINK

    def test_retry_attempts_just_below_max(self):
        """Retry attempts == 1 (< 2) is allowed for retry."""
        guard = SafetyGuard(max_retries=2)
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
            retry_attempts=1,
        )
        assert result.decision == GuardDecision.APPROVE
        assert result.final_action == RecoveryAction.RETRY
        assert result.rule_id == SafetyRuleId.APPROVED

    def test_custom_threshold_configuration(self):
        """Custom min_confidence and max_retries can be passed to constructor."""
        custom_guard = SafetyGuard(min_confidence=0.90, max_retries=5)
        assert custom_guard.min_confidence == 0.90
        assert custom_guard.max_retries == 5

        # 0.85 is below 0.90 -> LOW_CONFIDENCE
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        res = custom_guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
            retry_attempts=0,
        )
        assert res.rule_id == SafetyRuleId.LOW_CONFIDENCE

    def test_transaction_model_instance_input(self):
        """SafetyGuard accepts SQLAlchemy Transaction instance for transaction_status."""
        guard = SafetyGuard()
        analysis = _make_analysis(failure_category="NETWORK_ERROR", is_transient_failure=True)
        rec = _make_decision(action=RecoveryAction.RETRY, confidence=0.85)

        # Model instance with status CAPTURED
        txn = Transaction(
            razorpay_payment_id="pay_ModelCaptured001",
            amount=50000,
            status="CAPTURED",
        )
        result = guard.evaluate(
            transaction_status=txn,
            analysis=analysis,
            customer_history=_make_customer_history(),
            recovery_decision=rec,
        )
        assert result.decision == GuardDecision.STOP
        assert result.final_action == RecoveryAction.STOP
        assert result.rule_id == SafetyRuleId.ALREADY_CAPTURED

    def test_valid_reminder_approved_when_context_present(self):
        """REMINDER is approved when customer ID and valid context exist."""
        guard = SafetyGuard()
        analysis = _make_analysis(
            failure_category="AUTHENTICATION_FAILURE",
            customer_id="cust_ValidUser001",
            amount=10000,
        )
        history = _make_customer_history(customer_id="cust_ValidUser001")
        rec = _make_decision(action=RecoveryAction.REMINDER, confidence=0.82)

        result = guard.evaluate(
            transaction_status=TransactionStatus.FAILED,
            analysis=analysis,
            customer_history=history,
            recovery_decision=rec,
        )
        assert result.decision == GuardDecision.APPROVE
        assert result.final_action == RecoveryAction.REMINDER
        assert result.rule_id == SafetyRuleId.APPROVED

    def test_schema_serialization_and_validation(self):
        """SafetyDecision serializes cleanly to dict and JSON and adheres to schema."""
        decision = SafetyDecision(
            decision=GuardDecision.OVERRIDE,
            final_action=RecoveryAction.PAYMENT_LINK,
            reason="Retries exhausted; falling back to payment link",
            rule_id=SafetyRuleId.RETRY_LIMIT_REACHED,
        )
        dumped = decision.model_dump()
        assert dumped["decision"] == "OVERRIDE"
        assert dumped["final_action"] == "PAYMENT_LINK"
        assert dumped["rule_id"] == "RETRY_LIMIT_REACHED"
        assert len(dumped["reason"]) > 0

        json_str = decision.model_dump_json()
        assert "RETRY_LIMIT_REACHED" in json_str
