"""Phase 4 — LLM Decision Engine Tests.

All tests use MockLLMClient — no real LLM API calls are made.
These tests verify the Decision Engine's advisory recommendation behavior.
They do NOT test safety enforcement, which is Phase 5's responsibility.

"LLM recommends. Deterministic safety guard decides."
"""

import json
import pytest
from typing import Optional
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.core.database import init_db
from app.models.transaction import Transaction
from app.repositories.customer_repository import CustomerRepository
from app.schemas.analysis import PaymentAnalysis
from app.services.llm.schemas import RecoveryAction, RecoveryDecision, create_fallback_decision
from app.services.llm.decision_engine import DecisionEngine
from app.services.llm.prompts import format_analysis_context, SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Mock LLM Client
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Mock LLM client for deterministic testing.

    Returns a preconfigured response string, or raises a preconfigured
    exception, without making any external API calls.
    """

    def __init__(
        self,
        response: Optional[str] = None,
        exception: Optional[Exception] = None,
    ):
        self.response = response
        self.exception = exception
        self.last_system_prompt: Optional[str] = None
        self.last_user_content: Optional[str] = None
        self.call_count: int = 0

    def generate_decision(self, system_prompt: str, user_content: str) -> str:
        self.last_system_prompt = system_prompt
        self.last_user_content = user_content
        self.call_count += 1
        if self.exception is not None:
            raise self.exception
        return self.response or ""


# ---------------------------------------------------------------------------
# Test Fixtures
# ---------------------------------------------------------------------------


def _make_analysis(
    payment_id: str = "pay_Test001",
    amount: int = 500000,
    currency: str = "INR",
    payment_method: str = "card",
    failure_category: str = "NETWORK_ERROR",
    failure_code: str = "GATEWAY_ERROR",
    failure_description: str = "Network error during payment processing",
    attempt_count_24h: int = 1,
    previous_successful_payments: int = 4,
    active_risk_flags: list | None = None,
    eligible_for_analysis: bool = True,
    is_transient_failure: bool = True,
    requires_step_up_auth: bool = False,
    is_already_captured: bool = False,
    is_already_recovered: bool = False,
    customer_id: str | None = "cust_Test001",
) -> PaymentAnalysis:
    """Create a test PaymentAnalysis with sensible defaults."""
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
        recovery_context={
            "eligible_for_analysis": eligible_for_analysis,
            "is_transient_failure": is_transient_failure,
            "requires_step_up_auth": requires_step_up_auth,
            "is_already_captured": is_already_captured,
            "is_already_recovered": is_already_recovered,
        },
    )


def _valid_response(action: str, confidence: float = 0.85, rationale: str = "Test rationale") -> str:
    """Build a valid JSON response string."""
    return json.dumps({
        "action": action,
        "confidence": confidence,
        "rationale": rationale,
    })


# ---------------------------------------------------------------------------
# Tests A–D: Valid Recommendations
# ---------------------------------------------------------------------------


class TestValidRecommendations:
    """Verify that valid LLM responses parse into correct RecoveryDecision objects."""

    def test_a_valid_retry_recommendation(self):
        """Test A: Valid RETRY recommendation parses correctly."""
        mock = MockLLMClient(response=_valid_response("RETRY", 0.90, "Transient network error; retry likely to succeed"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.RETRY
        assert decision.confidence == 0.90
        assert "Transient network error" in decision.rationale

    def test_b_valid_payment_link_recommendation(self):
        """Test B: Valid PAYMENT_LINK recommendation parses correctly."""
        mock = MockLLMClient(response=_valid_response("PAYMENT_LINK", 0.75, "Card declined; alternative method may work"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(failure_category="CARD_DECLINED")

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.PAYMENT_LINK
        assert decision.confidence == 0.75
        assert "Card declined" in decision.rationale

    def test_c_valid_reminder_recommendation(self):
        """Test C: Valid REMINDER recommendation parses correctly."""
        mock = MockLLMClient(response=_valid_response("REMINDER", 0.60, "Customer session timed out; gentle reminder appropriate"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(failure_category="PAYMENT_TIMEOUT")

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.REMINDER
        assert decision.confidence == 0.60
        assert "session timed out" in decision.rationale

    def test_d_valid_stop_recommendation(self):
        """Test D: Valid STOP recommendation parses correctly."""
        mock = MockLLMClient(response=_valid_response("STOP", 0.95, "Fraud risk detected; cease recovery"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(failure_category="FRAUD_RISK")

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.95
        assert "Fraud risk" in decision.rationale


# ---------------------------------------------------------------------------
# Tests E–K: Schema & Validation Rejections → Safe Fallback
# ---------------------------------------------------------------------------


class TestValidationRejections:
    """Verify that invalid LLM output triggers a safe STOP fallback recommendation."""

    def test_e_invalid_action_value(self):
        """Test E: Invalid action ('retry_payment', 'REFUND') triggers STOP fallback."""
        for bad_action in ["retry_payment", "REFUND", "send_payment_link", "ASK_CUSTOMER", "NO_ACTION"]:
            mock = MockLLMClient(response=json.dumps({
                "action": bad_action,
                "confidence": 0.80,
                "rationale": "Test rationale",
            }))
            engine = DecisionEngine(llm_client=mock)
            analysis = _make_analysis()

            decision = engine.recommend_action(analysis)

            assert decision.action == RecoveryAction.STOP
            assert decision.confidence == 0.0

    def test_f_missing_action(self):
        """Test F: Missing action field triggers STOP fallback."""
        mock = MockLLMClient(response=json.dumps({
            "confidence": 0.80,
            "rationale": "Missing action field",
        }))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_g_missing_confidence(self):
        """Test G: Missing confidence field triggers STOP fallback."""
        mock = MockLLMClient(response=json.dumps({
            "action": "RETRY",
            "rationale": "Missing confidence",
        }))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_h_confidence_below_zero(self):
        """Test H: Confidence < 0.0 triggers STOP fallback."""
        mock = MockLLMClient(response=json.dumps({
            "action": "RETRY",
            "confidence": -0.5,
            "rationale": "Negative confidence",
        }))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_i_confidence_above_one(self):
        """Test I: Confidence > 1.0 triggers STOP fallback."""
        mock = MockLLMClient(response=json.dumps({
            "action": "RETRY",
            "confidence": 1.5,
            "rationale": "Over-confident",
        }))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_j_empty_rationale(self):
        """Test J: Empty rationale triggers STOP fallback."""
        mock = MockLLMClient(response=json.dumps({
            "action": "RETRY",
            "confidence": 0.80,
            "rationale": "",
        }))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_k_malformed_json(self):
        """Test K: Malformed JSON triggers STOP fallback."""
        mock = MockLLMClient(response="this is not json at all {{{")
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0


# ---------------------------------------------------------------------------
# Tests L–P: Provider Failures → Safe Fallback
# ---------------------------------------------------------------------------


class TestProviderFailures:
    """Verify that LLM provider errors always produce a safe STOP fallback."""

    def test_l_llm_timeout(self):
        """Test L: LLM timeout triggers STOP fallback."""
        mock = MockLLMClient(exception=TimeoutError("Request timed out after 10s"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0
        assert "timeout" in decision.rationale.lower()

    def test_m_llm_api_failure(self):
        """Test M: LLM API HTTP 500 failure triggers STOP fallback."""
        mock = MockLLMClient(exception=RuntimeError("LLM provider error (HTTP 500): Internal Server Error"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_n_empty_provider_response(self):
        """Test N: Empty provider response triggers STOP fallback."""
        mock = MockLLMClient(response="")
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_o_unexpected_provider_exception(self):
        """Test O: Unexpected provider exception triggers STOP fallback."""
        mock = MockLLMClient(exception=ConnectionError("DNS resolution failed"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_p_fallback_guarantees_stop_zero_confidence(self):
        """Test P: Fallback always guarantees action=STOP, confidence=0.0."""
        fallback = create_fallback_decision("test fallback")
        assert fallback.action == RecoveryAction.STOP
        assert fallback.confidence == 0.0
        assert fallback.rationale == "test fallback"

        # Also test via engine with no client
        engine = DecisionEngine(llm_client=None)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0


# ---------------------------------------------------------------------------
# Phase 4 Boundary Checks
# ---------------------------------------------------------------------------


class TestPhase4Boundaries:
    """Verify Phase 4 stays within its advisory role and does not
    modify transaction state or execute payment actions."""

    def test_llm_cannot_change_transaction_status(self):
        """LLM recommendation does NOT change Transaction.status."""
        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
        )
        init_db(bind_engine=test_engine)
        TestSession = sessionmaker(bind=test_engine)
        session = TestSession()

        try:
            repo = CustomerRepository(session)
            repo.upsert_failed_transaction(
                razorpay_payment_id="pay_Boundary001",
                customer_id="cust_Boundary001",
                amount=100000,
                currency="INR",
                failure_category="NETWORK_ERROR",
            )
            session.commit()

            # Verify transaction is FAILED
            txn = session.query(Transaction).filter_by(
                razorpay_payment_id="pay_Boundary001"
            ).first()
            assert txn is not None
            assert txn.status == "FAILED"

            # Run Decision Engine — should NOT change status
            mock = MockLLMClient(response=_valid_response("RETRY", 0.99, "High confidence retry"))
            engine = DecisionEngine(llm_client=mock)

            analysis = _make_analysis(
                payment_id="pay_Boundary001",
                customer_id="cust_Boundary001",
            )
            decision = engine.recommend_action(analysis)

            # Decision should be RETRY recommendation
            assert decision.action == RecoveryAction.RETRY

            # Transaction status MUST remain FAILED — the engine has no write access
            session.refresh(txn)
            assert txn.status == "FAILED"
        finally:
            session.close()

    def test_llm_cannot_execute_razorpay_actions(self):
        """LLM recommendation is a data object — it has no execute() method
        and cannot trigger Razorpay API calls."""
        mock = MockLLMClient(response=_valid_response("RETRY", 0.99, "Execute retry"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        # RecoveryDecision is a Pydantic model with no execution methods
        assert isinstance(decision, RecoveryDecision)
        assert not hasattr(decision, "execute")
        assert not hasattr(decision, "run")
        assert not hasattr(decision, "apply")
        assert not callable(getattr(decision, "action", None))

    def test_active_risk_flags_passed_as_context(self):
        """Active risk flags are included in the LLM prompt as context."""
        mock = MockLLMClient(response=_valid_response("STOP", 0.95, "Risk flags present"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(
            active_risk_flags=["FRAUD_SUSPICION", "CHARGEBACK_HISTORY"],
        )

        engine.recommend_action(analysis)

        # Verify the LLM received the risk flags in its context
        assert mock.last_user_content is not None
        context = json.loads(mock.last_user_content)
        assert "FRAUD_SUSPICION" in context["active_risk_flags"]
        assert "CHARGEBACK_HISTORY" in context["active_risk_flags"]

    def test_ineligible_transaction_returns_stop_without_llm_call(self):
        """Ineligible transaction returns STOP recommendation without calling LLM
        (cost optimization, not safety enforcement)."""
        mock = MockLLMClient(response=_valid_response("RETRY", 0.99, "Should not reach"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(eligible_for_analysis=False)

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0
        assert mock.call_count == 0  # LLM was never called

    def test_data_sanitization_strips_pii(self):
        """Context sent to LLM does NOT contain internal IDs or PII fields."""
        mock = MockLLMClient(response=_valid_response("RETRY", 0.80, "Clean context"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        engine.recommend_action(analysis)

        assert mock.last_user_content is not None
        context = json.loads(mock.last_user_content)

        # Must NOT contain internal database IDs
        assert "transaction_id" not in context
        assert "razorpay_payment_id" not in context
        assert "razorpay_order_id" not in context
        assert "customer_id" not in context

        # Must contain domain-relevant fields
        assert "amount_paise" in context
        assert "failure_category" in context
        assert "active_risk_flags" in context
        assert "recovery_context" in context

    def test_no_secrets_in_prompt(self):
        """System prompt and user context must not contain API keys or secrets."""
        mock = MockLLMClient(response=_valid_response("RETRY", 0.80, "No secrets"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        engine.recommend_action(analysis)

        # Check system prompt
        assert mock.last_system_prompt is not None
        prompt_lower = mock.last_system_prompt.lower()
        assert "api_key" not in prompt_lower
        assert "webhook_secret" not in prompt_lower
        assert "gemini_api_key" not in prompt_lower
        assert "anthropic" not in prompt_lower

        # Check user context
        context_lower = mock.last_user_content.lower()
        assert "api_key" not in context_lower
        assert "secret" not in context_lower
        assert "cvv" not in context_lower


# ---------------------------------------------------------------------------
# Context Evaluation Fixtures
# ---------------------------------------------------------------------------


class TestContextEvaluation:
    """Verify the Decision Engine processes context correctly and passes
    appropriate data to the LLM for different failure scenarios."""

    def test_case_1_transient_failure_retry(self):
        """Case 1: Transient network error with low attempts and good history → RETRY."""
        mock = MockLLMClient(response=_valid_response(
            "RETRY", 0.92,
            "Transient network error with only 1 attempt and 4 successful payments; retry likely to succeed",
        ))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(
            amount=500000,
            failure_category="NETWORK_ERROR",
            attempt_count_24h=1,
            previous_successful_payments=4,
            active_risk_flags=[],
            is_transient_failure=True,
        )

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.RETRY
        assert decision.confidence >= 0.8
        # Verify context was passed correctly
        context = json.loads(mock.last_user_content)
        assert context["failure_category"] == "NETWORK_ERROR"
        assert context["attempt_count_24h"] == 1
        assert context["recovery_context"]["is_transient_failure"] is True

    def test_case_2_repeated_failures_payment_link(self):
        """Case 2: Repeated failures suggest payment link instead of retry."""
        mock = MockLLMClient(response=_valid_response(
            "PAYMENT_LINK", 0.78,
            "3 attempts in 24h with card decline; alternative payment method may work",
        ))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(
            failure_category="CARD_DECLINED",
            attempt_count_24h=3,
            is_transient_failure=False,
        )

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.PAYMENT_LINK
        context = json.loads(mock.last_user_content)
        assert context["attempt_count_24h"] == 3

    def test_case_3_risk_flag_ineligible_stop(self):
        """Case 3: Active risk flag with eligible_for_analysis=False →
        Engine returns STOP without calling LLM."""
        mock = MockLLMClient(response=_valid_response("RETRY", 0.99, "Should not reach"))
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis(
            active_risk_flags=["fraud_risk"],
            eligible_for_analysis=False,
        )

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0
        assert mock.call_count == 0

    def test_json_wrapped_in_markdown_code_fence(self):
        """LLM wraps JSON in markdown code fence — engine strips it."""
        fenced_response = '```json\n{"action": "RETRY", "confidence": 0.85, "rationale": "Code fence test"}\n```'
        mock = MockLLMClient(response=fenced_response)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.RETRY
        assert decision.confidence == 0.85

    def test_json_wrapped_in_plain_code_fence(self):
        """LLM wraps JSON in plain code fence (no 'json' tag) — engine strips it."""
        fenced_response = '```\n{"action": "PAYMENT_LINK", "confidence": 0.70, "rationale": "Plain fence"}\n```'
        mock = MockLLMClient(response=fenced_response)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.PAYMENT_LINK
        assert decision.confidence == 0.70

    def test_json_wrapped_in_code_fence_with_surrounding_text(self):
        """LLM wraps JSON in code fence with leading and trailing conversational text."""
        raw = (
            "Here is the recommended recovery action based on analysis:\n"
            "```json\n"
            '{"action": "RETRY", "confidence": 0.88, "rationale": "Network glitch; retry is safe."}\n'
            "```\n"
            "Hope this helps resolve the payment issue."
        )
        mock = MockLLMClient(response=raw)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.RETRY
        assert decision.confidence == 0.88
        assert "Network glitch" in decision.rationale

    def test_unfenced_json_with_leading_and_trailing_text(self):
        """LLM returns raw JSON object surrounded by brief conversational text without fences."""
        raw = (
            "Recommendation:\n"
            '{"action": "STOP", "confidence": 0.95, "rationale": "Fraud pattern detected; stop recovery."}\n'
            "End of recommendation."
        )
        mock = MockLLMClient(response=raw)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.95
        assert "Fraud pattern" in decision.rationale

    def test_json_with_harmless_whitespace_and_newlines(self):
        """LLM returns JSON with irregular leading/trailing whitespace, tabs, and newlines."""
        raw = '  \n\t  \n{"action": "REMINDER", "confidence": 0.65, "rationale": "Session expired."}  \n\t  '
        mock = MockLLMClient(response=raw)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.REMINDER
        assert decision.confidence == 0.65

    def test_json_array_rejected_with_fallback_stop(self):
        """LLM returns a JSON array instead of an object — must trigger safe STOP fallback."""
        raw = '[{"action": "RETRY", "confidence": 0.90, "rationale": "Array item"}]'
        mock = MockLLMClient(response=raw)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0

    def test_malformed_unparseable_json_with_braces_triggers_fallback_stop(self):
        """LLM returns text with curly braces that is NOT valid JSON — must trigger safe STOP fallback."""
        raw = "Decision summary: {action: RETRY, not real json here!}"
        mock = MockLLMClient(response=raw)
        engine = DecisionEngine(llm_client=mock)
        analysis = _make_analysis()

        decision = engine.recommend_action(analysis)

        assert decision.action == RecoveryAction.STOP
        assert decision.confidence == 0.0


# ---------------------------------------------------------------------------
# Schema Unit Tests
# ---------------------------------------------------------------------------


class TestRecoverySchemas:
    """Direct unit tests for RecoveryAction and RecoveryDecision schemas."""

    def test_recovery_action_enum_values(self):
        """RecoveryAction enum has exactly 4 allowed values."""
        assert set(RecoveryAction) == {
            RecoveryAction.RETRY,
            RecoveryAction.PAYMENT_LINK,
            RecoveryAction.REMINDER,
            RecoveryAction.STOP,
        }

    def test_recovery_decision_rejects_invalid_action_string(self):
        """RecoveryDecision rejects arbitrary action strings."""
        with pytest.raises(Exception):
            RecoveryDecision(
                action="REFUND",
                confidence=0.5,
                rationale="Invalid action",
            )

    def test_recovery_decision_rejects_negative_confidence(self):
        """RecoveryDecision rejects confidence < 0."""
        with pytest.raises(Exception):
            RecoveryDecision(
                action=RecoveryAction.RETRY,
                confidence=-0.1,
                rationale="Negative confidence",
            )

    def test_recovery_decision_rejects_confidence_over_one(self):
        """RecoveryDecision rejects confidence > 1."""
        with pytest.raises(Exception):
            RecoveryDecision(
                action=RecoveryAction.RETRY,
                confidence=1.01,
                rationale="Over one",
            )

    def test_recovery_decision_rejects_empty_rationale(self):
        """RecoveryDecision rejects empty rationale."""
        with pytest.raises(Exception):
            RecoveryDecision(
                action=RecoveryAction.RETRY,
                confidence=0.5,
                rationale="",
            )

    def test_format_analysis_context_excludes_sensitive_fields(self):
        """format_analysis_context must exclude internal IDs and PII."""
        analysis = _make_analysis()
        context_str = format_analysis_context(analysis)
        context = json.loads(context_str)

        # Should NOT contain
        assert "transaction_id" not in context
        assert "razorpay_payment_id" not in context
        assert "customer_id" not in context

        # Should contain
        assert context["amount_paise"] == 500000
        assert context["failure_category"] == "NETWORK_ERROR"
        assert context["recovery_context"]["is_transient_failure"] is True


# ---------------------------------------------------------------------------
# Gemini Client Timeout Tests (Mocked SDK)
# ---------------------------------------------------------------------------


class TestGeminiClientTimeout:
    """Verify that GeminiLLMClient properly configures and passes the
    configured timeout in milliseconds to the google-genai SDK using HttpOptions."""

    def test_gemini_client_receives_configured_timeout(self, monkeypatch):
        """Verify GeminiLLMClient initializes genai.Client with HttpOptions(timeout=ms)."""
        from unittest.mock import MagicMock
        from app.services.llm.client import GeminiLLMClient

        mock_client_cls = MagicMock()
        monkeypatch.setattr("google.genai.Client", mock_client_cls)

        # Instantiate with custom timeout (e.g., 14.5 seconds)
        client = GeminiLLMClient(
            api_key="test_mock_api_key_123",
            timeout=14.5,
            model="gemini-2.5-flash",
        )

        # Verify genai.Client was called with http_options having 14500 ms timeout
        mock_client_cls.assert_called_once()
        call_kwargs = mock_client_cls.call_args[1]
        assert call_kwargs["api_key"] == "test_mock_api_key_123"
        assert call_kwargs["http_options"].timeout == 14500

    def test_gemini_client_passes_timeout_to_generate_content(self, monkeypatch):
        """Verify GeminiLLMClient.generate_decision passes HttpOptions to GenerateContentConfig."""
        from unittest.mock import MagicMock
        from app.services.llm.client import GeminiLLMClient

        mock_client_instance = MagicMock()
        mock_client_cls = MagicMock(return_value=mock_client_instance)
        monkeypatch.setattr("google.genai.Client", mock_client_cls)

        mock_response = MagicMock()
        mock_response.text = '{"action": "RETRY", "confidence": 0.9, "rationale": "ok"}'
        mock_client_instance.models.generate_content.return_value = mock_response

        client = GeminiLLMClient(
            api_key="test_mock_api_key_123",
            timeout=7.5,
        )

        result = client.generate_decision(
            system_prompt="system",
            user_content="user",
        )

        assert result == '{"action": "RETRY", "confidence": 0.9, "rationale": "ok"}'
        mock_client_instance.models.generate_content.assert_called_once()
        call_kwargs = mock_client_instance.models.generate_content.call_args[1]
        config = call_kwargs["config"]
        assert config.http_options.timeout == 7500
