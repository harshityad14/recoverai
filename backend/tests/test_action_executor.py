"""Phase 6 — Action Executor and Razorpay Test Mode Tests.

Verifies the execution layer that receives ONLY the final action produced by the
deterministic Safety Guard and executes permitted recovery operations in Test Mode.

CORE PRINCIPLE:
- Safety Guard is the final authority.
- The Action Executor must NEVER execute raw Gemini recommendations.
- Payment Link CREATED != payment recovered.
- Only Test Mode is permitted (Live Mode keys strictly prohibited).
- No real external Razorpay API calls are made during the normal test suite.

"LLM recommends. Deterministic safety guard decides. Action Executor dispatches."
"""

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch
import httpx
import pytest
from sqlalchemy.orm import Session

from app.models.retry_history import RetryHistory
from app.models.transaction import Transaction
from app.repositories.customer_repository import CustomerRepository
from app.schemas.action import ActionResult
from app.schemas.safety import GuardDecision, SafetyDecision, SafetyRuleId
from app.schemas.transaction import TransactionStatus
from app.services.action_executor import ActionExecutor
from app.services.llm.schemas import RecoveryAction, RecoveryDecision
from app.services.razorpay_client import (
    RazorpayAPIError,
    RazorpayAuthenticationError,
    RazorpayClient,
    RazorpayNetworkError,
    RazorpayResponseError,
    RazorpaySecurityError,
    RazorpayTimeoutError,
)
from app.workers.webhook_worker import WebhookWorker


# ---------------------------------------------------------------------------
# Test Helpers & Mock Razorpay Client
# ---------------------------------------------------------------------------


class MockRazorpayClient(RazorpayClient):
    """Offline Mock RazorpayClient for testing ActionExecutor without network calls."""

    def __init__(
        self,
        key_id: str = "rzp_test_mock_key_12345",
        key_secret: str = "mock_secret_12345",
        response_data: Optional[Dict[str, Any]] = None,
        exception_to_raise: Optional[Exception] = None,
    ):
        super().__init__(key_id=key_id, key_secret=key_secret)
        self.response_data = response_data or {
            "id": "plink_TestMock123456",
            "short_url": "https://rzp.io/i/TestMock123",
            "status": "created",
            "amount": 50000,
            "currency": "INR",
        }
        self.exception_to_raise = exception_to_raise
        self.call_count: int = 0
        self.last_payload: Dict[str, Any] = {}

    def create_payment_link(self, **kwargs) -> Dict[str, Any]:
        self.call_count += 1
        self.last_payload = kwargs
        if self.exception_to_raise:
            raise self.exception_to_raise
        return self.response_data


def _make_transaction(
    payment_id: str = "pay_FailTxn001",
    amount: int = 50000,
    currency: str = "INR",
    status: str = "FAILED",
    customer_id: str = "cust_User001",
    order_id: str = "order_Ord001",
) -> Transaction:
    """Create a Transaction entity for testing."""
    return Transaction(
        id=f"txn-uuid-{payment_id}",
        razorpay_payment_id=payment_id,
        razorpay_order_id=order_id,
        customer_id=customer_id,
        amount=amount,
        currency=currency,
        status=status,
    )


def _make_safety_decision(
    decision: GuardDecision = GuardDecision.APPROVE,
    final_action: RecoveryAction = RecoveryAction.PAYMENT_LINK,
    rule_id: SafetyRuleId = SafetyRuleId.APPROVED,
    reason: str = "Approved recovery action",
) -> SafetyDecision:
    """Create a test SafetyDecision."""
    return SafetyDecision(
        decision=decision,
        final_action=final_action,
        rule_id=rule_id,
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Test Cases 1–24 (Specification Requirements)
# ---------------------------------------------------------------------------


class TestActionExecutorCore:
    """Core ActionExecutor unit tests (requirements 1–24)."""

    def test_1_approve_payment_link_executes(self, db_session: Session):
        """Test 1: APPROVE + PAYMENT_LINK executes and creates a payment link."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_001", amount=75000)
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision(
            decision=GuardDecision.APPROVE,
            final_action=RecoveryAction.PAYMENT_LINK,
        )

        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is True
        assert result.action == RecoveryAction.PAYMENT_LINK
        assert result.external_id == "plink_TestMock123456"
        assert result.payment_link_url == "https://rzp.io/i/TestMock123"
        assert mock_client.call_count == 1

    def test_2_approve_stop_performs_no_external_action(self, db_session: Session):
        """Test 2: APPROVE + STOP performs no external action."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_002")
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision(
            decision=GuardDecision.APPROVE,
            final_action=RecoveryAction.STOP,
        )

        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is True
        assert result.action == RecoveryAction.STOP
        assert mock_client.call_count == 0
        assert tx.status == "STOPPED"

    def test_3_override_stop_performs_no_external_action(self, db_session: Session):
        """Test 3: OVERRIDE + STOP performs no external action."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_003")
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision(
            decision=GuardDecision.OVERRIDE,
            final_action=RecoveryAction.STOP,
            rule_id=SafetyRuleId.LOW_CONFIDENCE,
        )

        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is True
        assert result.action == RecoveryAction.STOP
        assert mock_client.call_count == 0
        assert tx.status == "STOPPED"

    def test_4_unexpected_safety_decision_fails_closed(self, db_session: Session):
        """Test 4: Unexpected decision combinations fail closed without executing."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_004")

        # OVERRIDE with RETRY is unexpected and unauthorized
        safety_dec = _make_safety_decision(
            decision=GuardDecision.OVERRIDE,
            final_action=RecoveryAction.RETRY,
        )

        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "UNEXPECTED_DECISION_COMBINATION"
        assert mock_client.call_count == 0

    def test_5_payment_link_request_contains_correct_amount(self, db_session: Session):
        """Test 5: Payment Link request contains the exact transaction amount."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_005", amount=129900)
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision(
            decision=GuardDecision.APPROVE,
            final_action=RecoveryAction.PAYMENT_LINK,
        )
        executor.execute(tx, safety_dec, db=db_session)

        assert mock_client.last_payload["amount"] == 129900

    def test_6_payment_link_amount_uses_smallest_currency_unit(self, db_session: Session):
        """Test 6: Payment Link amount is in subunits (paise for INR, integer)."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_006", amount=4999)  # Rs 49.99 = 4999 paise
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision(
            decision=GuardDecision.APPROVE,
            final_action=RecoveryAction.PAYMENT_LINK,
        )
        executor.execute(tx, safety_dec, db=db_session)

        assert isinstance(mock_client.last_payload["amount"], int)
        assert mock_client.last_payload["amount"] == 4999

    def test_7_payment_link_gets_unique_reference_id(self, db_session: Session):
        """Test 7: Each payment link gets a unique, non-empty reference_id."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx1 = _make_transaction(payment_id="pay_007a")
        tx2 = _make_transaction(payment_id="pay_007b")
        db_session.add_all([tx1, tx2])
        db_session.commit()

        safety_dec = _make_safety_decision()

        res1 = executor.execute(tx1, safety_dec, db=db_session)
        ref1 = mock_client.last_payload["reference_id"]

        res2 = executor.execute(tx2, safety_dec, db=db_session)
        ref2 = mock_client.last_payload["reference_id"]

        assert ref1 is not None and len(ref1) > 0
        assert ref2 is not None and len(ref2) > 0
        assert ref1 != ref2

    def test_8_payment_link_result_is_stored(self, db_session: Session):
        """Test 8: Payment link ID and URL are persisted on Transaction and RetryHistory."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_008")
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision()
        result = executor.execute(tx, safety_dec, db=db_session)

        db_session.refresh(tx)
        assert tx.payment_link_id == "plink_TestMock123456"
        assert tx.payment_link_url == "https://rzp.io/i/TestMock123"
        assert tx.status == "RECOVERY_PENDING"

        # Check RetryHistory record
        history = db_session.query(RetryHistory).filter_by(transaction_id=tx.id).all()
        assert len(history) == 1
        assert history[0].action == "PAYMENT_LINK"
        assert history[0].external_id == "plink_TestMock123456"
        assert history[0].result == "LINK_CREATED"

    def test_9_duplicate_execution_does_not_create_duplicate_links(self, db_session: Session):
        """Test 9: Calling execute twice on the same transaction reuses the existing link."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_009")
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision()

        # First execution: creates link
        res1 = executor.execute(tx, safety_dec, db=db_session)
        assert res1.idempotent is False
        assert mock_client.call_count == 1

        # Second execution: reuses link without calling Razorpay API again
        res2 = executor.execute(tx, safety_dec, db=db_session)
        assert res2.success is True
        assert res2.idempotent is True
        assert res2.external_id == res1.external_id
        assert mock_client.call_count == 1  # No second call!

    def test_10_razorpay_authentication_failure_is_handled(self, db_session: Session):
        """Test 10: Razorpay HTTP 401 returns structured failure without crashing."""
        mock_client = MockRazorpayClient(exception_to_raise=RazorpayAuthenticationError())
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_010")

        safety_dec = _make_safety_decision()
        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "AUTHENTICATION_FAILURE"
        assert "authentication" in (result.error_message or "").lower()

    def test_11_razorpay_timeout_is_handled(self, db_session: Session):
        """Test 11: Razorpay timeout returns structured GATEWAY_TIMEOUT without crashing."""
        mock_client = MockRazorpayClient(exception_to_raise=RazorpayTimeoutError())
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_011")

        safety_dec = _make_safety_decision()
        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "GATEWAY_TIMEOUT"

    def test_12_razorpay_network_failure_is_handled(self, db_session: Session):
        """Test 12: Network failure returns structured NETWORK_FAILURE."""
        mock_client = MockRazorpayClient(exception_to_raise=RazorpayNetworkError())
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_012")

        safety_dec = _make_safety_decision()
        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "NETWORK_FAILURE"

    def test_13_razorpay_malformed_response_is_handled(self, db_session: Session):
        """Test 13: Non-JSON / malformed response returns INVALID_RESPONSE."""
        mock_client = MockRazorpayClient(exception_to_raise=RazorpayResponseError())
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_013")

        safety_dec = _make_safety_decision()
        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "INVALID_RESPONSE"

    def test_14_retry_does_not_call_an_invented_razorpay_endpoint(self, db_session: Session):
        """Test 14: RETRY returns ACTION_NOT_SUPPORTED without calling any Razorpay API."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_014")

        safety_dec = _make_safety_decision(
            decision=GuardDecision.APPROVE,
            final_action=RecoveryAction.RETRY,
        )
        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "ACTION_NOT_SUPPORTED"
        assert mock_client.call_count == 0  # Never called Razorpay!

    def test_15_reminder_does_not_claim_success_without_supported_execution(self, db_session: Session):
        """Test 15: REMINDER returns NOT_IMPLEMENTED without fake success."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_015")

        safety_dec = _make_safety_decision(
            decision=GuardDecision.APPROVE,
            final_action=RecoveryAction.REMINDER,
        )
        result = executor.execute(tx, safety_dec, db=db_session)

        assert result.success is False
        assert result.error_code == "NOT_IMPLEMENTED"
        assert mock_client.call_count == 0

    def test_16_payment_link_creation_does_not_mark_transaction_recovered(self, db_session: Session):
        """Test 16: Creating a Payment Link leaves transaction in RECOVERY_PENDING, NOT RECOVERED."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_016", status="FAILED")
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision()
        executor.execute(tx, safety_dec, db=db_session)

        db_session.refresh(tx)
        assert tx.status == "RECOVERY_PENDING"
        assert tx.status != "RECOVERED"

    def test_17_payment_captured_after_recoverai_payment_link_produces_recovered(self, db_session: Session):
        """Test 17: payment.captured event correlating with a payment link transitions to RECOVERED."""
        repo = CustomerRepository(db_session)
        # Pre-seed a transaction in RECOVERY_PENDING with active payment link
        tx = _make_transaction(payment_id="pay_OrigFail017", status="RECOVERY_PENDING")
        tx.payment_link_id = "plink_RecLink017"
        db_session.add(tx)
        db_session.commit()

        # Webhook payload arrives for the payment link capture
        captured_tx = repo.mark_transaction_captured(
            razorpay_payment_id="pay_PaidViaLink017",
            amount=50000,
            currency="INR",
            payment_link_id="plink_RecLink017",
            notes={"transaction_id": tx.id, "recovered_by": "RecoverAI"},
        )

        assert captured_tx is not None
        assert captured_tx.id == tx.id
        assert captured_tx.status == "RECOVERED"

    def test_18_unrelated_payment_captured_produces_captured(self, db_session: Session):
        """Test 18: Organic payment.captured without RecoverAI recovery correlation remains CAPTURED."""
        repo = CustomerRepository(db_session)
        tx = _make_transaction(payment_id="pay_Organic018", status="FAILED")
        db_session.add(tx)
        db_session.commit()

        # Capture arrives without payment link notes or recovery action
        captured_tx = repo.mark_transaction_captured(
            razorpay_payment_id="pay_Organic018",
            amount=50000,
            currency="INR",
        )

        assert captured_tx is not None
        assert captured_tx.status == "CAPTURED"
        assert captured_tx.status != "RECOVERED"

    def test_19_delayed_payment_failed_does_not_overwrite_recovered(self, db_session: Session):
        """Test 19: Out-of-order delayed payment.failed cannot overwrite RECOVERED back to FAILED."""
        repo = CustomerRepository(db_session)
        tx = _make_transaction(payment_id="pay_Recovered019", status="RECOVERED")
        db_session.add(tx)
        db_session.commit()

        # Delayed failure webhook arrives
        upserted = repo.upsert_failed_transaction(
            razorpay_payment_id="pay_Recovered019",
            amount=50000,
            failure_category="NETWORK_ERROR",
        )

        assert upserted.status == "RECOVERED"

    def test_20_api_credentials_are_never_included_in_logs_or_results(self, db_session: Session):
        """Test 20: Secrets are excluded from ActionResult and error messages."""
        secret = "super_secret_rzp_pass_999"
        mock_client = MockRazorpayClient(
            key_secret=secret,
            exception_to_raise=RazorpayAuthenticationError(),
        )
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_020")

        result = executor.execute(tx, _make_safety_decision(), db=db_session)

        dumped = result.model_dump_json()
        assert secret not in dumped
        assert secret not in (result.error_message or "")

    def test_21_test_mode_configuration_is_used(self):
        """Test 21: RazorpayClient identifies and operates in Test Mode."""
        client = RazorpayClient(key_id="rzp_test_MyTestKey123", key_secret="test_secret")
        assert client.is_test_mode is True

    def test_22_live_mode_is_never_invoked(self):
        """Test 22: Initializing with a Live Mode key immediately raises RazorpaySecurityError."""
        with pytest.raises(RazorpaySecurityError, match="Live Mode is strictly prohibited"):
            RazorpayClient(key_id="rzp_live_ForbiddenLiveKey999", key_secret="live_secret")

    def test_23_action_executor_cannot_execute_raw_recovery_decision(self, db_session: Session):
        """Test 23: Passing a raw LLM RecoveryDecision fails closed."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_023")

        raw_llm_decision = RecoveryDecision(
            action=RecoveryAction.PAYMENT_LINK,
            confidence=0.99,
            rationale="Untrusted raw recommendation",
        )

        result = executor.execute(tx, raw_llm_decision, db=db_session)

        assert result.success is False
        assert result.error_code == "UNAUTHORIZED_DECISION_INPUT"
        assert mock_client.call_count == 0

    def test_24_repeated_execution_is_idempotent(self, db_session: Session):
        """Test 24: Repeated execution with active link yields identical, idempotent ActionResult."""
        mock_client = MockRazorpayClient()
        executor = ActionExecutor(razorpay_client=mock_client, db=db_session)
        tx = _make_transaction(payment_id="pay_024")
        db_session.add(tx)
        db_session.commit()

        safety_dec = _make_safety_decision()

        res1 = executor.execute(tx, safety_dec, db=db_session)
        res2 = executor.execute(tx, safety_dec, db=db_session)
        res3 = executor.execute(tx, safety_dec, db=db_session)

        assert res1.success is True
        assert res2.success is True
        assert res3.success is True
        assert res2.idempotent is True
        assert res3.idempotent is True
        assert res1.external_id == res2.external_id == res3.external_id
        assert mock_client.call_count == 1  # Exactly one API call across 3 executions


# ---------------------------------------------------------------------------
# RazorpayClient Direct Unit Tests (Offline HTTP Mocks)
# ---------------------------------------------------------------------------


class TestRazorpayClientDirect:
    """Direct tests for RazorpayClient request building and error handling."""

    @patch.object(httpx.Client, "post")
    def test_create_payment_link_success(self, mock_post):
        """Verify successful HTTP POST to /v1/payment_links with correct headers and auth."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.is_error = False
        mock_resp.json.return_value = {
            "id": "plink_H12345678",
            "short_url": "https://rzp.io/i/H123456",
            "status": "created",
        }
        mock_post.return_value = mock_resp

        client = RazorpayClient(key_id="rzp_test_123", key_secret="secret_123")
        res = client.create_payment_link(
            amount=10000,
            currency="INR",
            reference_id="rec_ref_001",
        )

        assert res["id"] == "plink_H12345678"
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        assert args[0] == "https://api.razorpay.com/v1/payment_links"
        assert kwargs["auth"] == ("rzp_test_123", "secret_123")
        assert kwargs["json"]["amount"] == 10000

    @patch.object(httpx.Client, "post")
    def test_create_payment_link_401_raises_auth_error(self, mock_post):
        """Verify HTTP 401 raises RazorpayAuthenticationError."""
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.is_error = True
        mock_post.return_value = mock_resp

        client = RazorpayClient(key_id="rzp_test_123", key_secret="bad_secret")
        with pytest.raises(RazorpayAuthenticationError):
            client.create_payment_link(amount=10000)

    @patch.object(httpx.Client, "post")
    def test_create_payment_link_timeout_raises_timeout_error(self, mock_post):
        """Verify request timeout raises RazorpayTimeoutError."""
        mock_post.side_effect = httpx.TimeoutException("Connection timed out")

        client = RazorpayClient(key_id="rzp_test_123", key_secret="secret_123")
        with pytest.raises(RazorpayTimeoutError):
            client.create_payment_link(amount=10000)
