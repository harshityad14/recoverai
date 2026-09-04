"""Phase 7 — End-to-End Recovery Pipeline Integration Tests.

Comprehensive deterministic test suite covering:
1. payment.failed enters recovery pipeline
2. eligible failure reaches Gemini
3. Gemini decision reaches SafetyGuard
4. only SafetyDecision reaches ActionExecutor
5. ineligible analysis bypasses Gemini
6. low-confidence decision stops
7. unsafe action stops
8. approved PAYMENT_LINK executes
9. Payment Link creation produces RECOVERY_PENDING
10. correlated payment.captured produces RECOVERED
11. unrelated payment.captured produces CAPTURED
12. delayed payment.failed cannot overwrite RECOVERED
13. duplicate payment.failed is idempotent
14. duplicate payment.captured is idempotent
15. Gemini failure fails safely
16. Razorpay failure records failed execution
17. unsupported RETRY never claims success
18. unsupported REMINDER never claims success
19. revenue_at_risk calculation is correct
20. recovered_revenue calculation is correct
21. recovery_rate calculation is correct
22. zero-denominator recovery rate handled
23. audit trail contains AI recommendation
24. audit trail contains Safety Guard decision
25. audit trail contains final action
26. audit trail contains execution outcome
27. no API secrets appear in persisted audit data
28. repeated processing produces deterministic outcome

CORE PRINCIPLES:
- Gemini is recommendation-only.
- Safety Guard is final authority.
- Action Executor receives ONLY SafetyDecision.
- Payment link created != recovered.
- Only causally correlated capture produces RECOVERED.
- Zero external API calls (offline mocks for LLM and Razorpay).
"""

import json
from typing import Any, Dict, Optional
import pytest
from sqlalchemy.orm import Session

from app.core.queue import WEBHOOK_QUEUE_NAME
from app.models.retry_history import RetryHistory
from app.models.risk_flag import RiskFlag
from app.models.transaction import Transaction
from app.repositories.customer_repository import CustomerRepository
from app.schemas.action import ActionResult
from app.schemas.safety import GuardDecision, SafetyDecision, SafetyRuleId
from app.schemas.taxonomy import FailureCategory
from app.schemas.transaction import TransactionStatus
from app.services.action_executor import ActionExecutor
from app.services.llm.decision_engine import DecisionEngine
from app.services.llm.schemas import RecoveryAction, RecoveryDecision
from app.services.metrics_service import RecoveryMetricsService
from app.services.razorpay_client import RazorpayAPIError, RazorpayClient
from app.services.safety_guard import SafetyGuard
from app.workers.webhook_worker import WebhookWorker
from tests.conftest import FakeRedis


# ---------------------------------------------------------------------------
# Test Mocks
# ---------------------------------------------------------------------------


class MockLLMClient:
    """Mock LLM client implementing LLMClient protocol."""

    def __init__(
        self,
        response_text: str = "",
        exception_to_raise: Optional[Exception] = None,
    ):
        self.response_text = response_text
        self.exception_to_raise = exception_to_raise
        self.calls: list = []

    def generate_decision(self, system_prompt: str, user_content: str) -> str:
        self.calls.append({"system_prompt": system_prompt, "user_content": user_content})
        if self.exception_to_raise:
            raise self.exception_to_raise
        return self.response_text


class MockRazorpayClient(RazorpayClient):
    """Mock Razorpay client for test mode link creation."""

    def __init__(
        self,
        key_id: str = "rzp_test_pipeline_mock",
        key_secret: str = "mock_secret_test",
        response_data: Optional[Dict[str, Any]] = None,
        exception_to_raise: Optional[Exception] = None,
    ):
        super().__init__(key_id=key_id, key_secret=key_secret)
        self.response_data = response_data or {
            "id": "plink_PipelineTest123",
            "short_url": "https://rzp.io/i/PipelineTest123",
            "status": "created",
            "amount": 20000,
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


def _build_failed_event(
    payment_id: str = "pay_Failed001",
    amount: int = 20000,
    error_code: str = "BAD_REQUEST_ERROR",
    error_description: str = "Payment timed out waiting for bank response",
    customer_id: str = "cust_User001",
    order_id: str = "order_Ord001",
    notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a Razorpay payment.failed webhook event payload."""
    return {
        "event_id": f"evt_{payment_id}",
        "event_type": "payment.failed",
        "account_id": "acc_Merchant001",
        "payload": {
            "entity": "event",
            "event": "payment.failed",
            "account_id": "acc_Merchant001",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": payment_id,
                        "order_id": order_id,
                        "amount": amount,
                        "currency": "INR",
                        "status": "failed",
                        "method": "upi",
                        "customer_id": customer_id,
                        "error_code": error_code,
                        "error_description": error_description,
                        "error_source": "bank",
                        "error_step": "payment_authorization",
                        "error_reason": "bank_timed_out",
                        "notes": notes or {},
                    }
                }
            },
            "created_at": 1700000000,
        },
    }


def _build_captured_event(
    payment_id: str = "pay_Cap001",
    amount: int = 20000,
    order_id: Optional[str] = "order_Ord001",
    customer_id: str = "cust_User001",
    payment_link_id: Optional[str] = None,
    notes: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a Razorpay payment.captured webhook event payload."""
    entity: Dict[str, Any] = {
        "id": payment_id,
        "order_id": order_id,
        "amount": amount,
        "currency": "INR",
        "status": "captured",
        "method": "upi",
        "customer_id": customer_id,
        "notes": notes or {},
    }
    if payment_link_id:
        entity["payment_link_id"] = payment_link_id

    return {
        "event_id": f"evt_{payment_id}",
        "event_type": "payment.captured",
        "account_id": "acc_Merchant001",
        "payload": {
            "entity": "event",
            "event": "payment.captured",
            "account_id": "acc_Merchant001",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": entity,
                }
            },
            "created_at": 1700000500,
        },
    }


# ---------------------------------------------------------------------------
# Test Suite: 28 Core Integration Requirements
# ---------------------------------------------------------------------------


class TestRecoveryPipeline:
    """Complete integration test suite for the RecoverAI Phase 7 pipeline."""

    def test_1_payment_failed_enters_recovery_pipeline(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 1: payment.failed webhook event enqueued in Redis enters recovery pipeline."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.90,
                "rationale": "High value recoverable bank timeout.",
            })
        )
        mock_rzp = MockRazorpayClient()

        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Enter001", amount=20000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result is not None
        assert result["status"] == "processed"
        assert result["event_type"] == "payment.failed"
        assert result["recovery_executed"] is True
        assert len(mock_llm.calls) == 1

    def test_2_eligible_failure_reaches_gemini(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 2: Eligible failure reaches Gemini decision engine with sanitized context."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.85,
                "rationale": "Eligible for payment link re-attempt.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Eligible002", amount=15000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        assert len(mock_llm.calls) == 1
        call_context = mock_llm.calls[0]["user_content"]
        assert "15000" in call_context
        assert "BANK_TIMEOUT" in call_context

    def test_3_gemini_decision_reaches_safety_guard(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 3: Gemini decision is passed to the SafetyGuard for validation."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.88,
                "rationale": "Recommended link creation.",
            })
        )
        guard = SafetyGuard()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            safety_guard=guard,
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Guard003", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        safety_dec = result["safety_decision"]
        assert safety_dec["decision"] == "APPROVE"
        assert safety_dec["final_action"] == "PAYMENT_LINK"
        assert safety_dec["rule_id"] == "APPROVED"

    def test_4_only_safety_decision_reaches_action_executor(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 4: ActionExecutor receives ONLY SafetyDecision and rejects raw RecoveryDecision."""
        executor = ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session)
        txn = Transaction(
            razorpay_payment_id="pay_RawTest004",
            amount=5000,
            status="FAILED",
        )
        db_session.add(txn)
        db_session.commit()

        raw_decision = RecoveryDecision(
            action=RecoveryAction.PAYMENT_LINK,
            confidence=0.99,
            rationale="Unverified LLM decision",
        )

        # Passing raw RecoveryDecision must fail closed with UNAUTHORIZED_DECISION_INPUT
        result = executor.execute(transaction=txn, safety_decision=raw_decision)
        assert result.success is False
        assert result.error_code == "UNAUTHORIZED_DECISION_INPUT"

    def test_5_ineligible_analysis_bypasses_gemini(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 5: Ineligible failure (e.g. fraud) stops immediately without calling Gemini."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({"action": "PAYMENT_LINK", "confidence": 0.90, "rationale": "test"})
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        # Create fraud failure event
        event = _build_failed_event(
            payment_id="pay_Fraud005",
            amount=5000,
            error_code="FRAUD_SUSPICION",
            error_description="Card reported stolen or fraudulent activity detected",
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        # Must not call Gemini
        assert len(mock_llm.calls) == 0
        assert result["status"] == "ineligible_stopped"
        assert result["transaction_status"] == "STOPPED"

    def test_6_low_confidence_decision_stops(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 6: Low-confidence decision (< 0.70) is overridden to STOP by SafetyGuard."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.45,  # Below 0.70 threshold
                "rationale": "Uncertain about customer payment intent.",
            })
        )
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_LowConf006", amount=8000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["safety_decision"]["decision"] == "OVERRIDE"
        assert result["safety_decision"]["final_action"] == "STOP"
        assert result["safety_decision"]["rule_id"] == "LOW_CONFIDENCE"
        assert mock_rzp.call_count == 0  # No link created

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_LowConf006").first()
        assert txn.status == "STOPPED"

    def test_7_unsafe_action_stops(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 7: Unsafe action on customer with active risk flag is blocked and stops recovery."""
        # Pre-seed active risk flag
        flag = RiskFlag(customer_id="cust_HighRisk007", flag="FRAUD_SUSPICION", active=True)
        db_session.add(flag)
        db_session.commit()

        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.95,
                "rationale": "Customer requested link.",
            })
        )
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(
            payment_id="pay_Unsafe007",
            amount=10000,
            customer_id="cust_HighRisk007",
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        # Ineligible analysis halts before Gemini
        assert len(mock_llm.calls) == 0
        assert mock_rzp.call_count == 0
        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Unsafe007").first()
        assert txn.status == "STOPPED"

    def test_8_approved_payment_link_executes(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 8: Approved PAYMENT_LINK executes through Razorpay Test Mode client."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.92,
                "rationale": "High value transient failure suitable for recovery link.",
            })
        )
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Exec008", amount=20000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["action_result"]["success"] is True
        assert result["action_result"]["action"] == "PAYMENT_LINK"
        assert result["action_result"]["external_id"] == "plink_PipelineTest123"
        assert mock_rzp.call_count == 1

    def test_9_payment_link_produces_recovery_pending(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 9: Payment Link creation produces RECOVERY_PENDING, NOT RECOVERED."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.88,
                "rationale": "Payment link approved.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Pending009", amount=20000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Pending009").first()
        assert txn.status == "RECOVERY_PENDING"
        assert txn.status != "RECOVERED"
        assert txn.payment_link_id == "plink_PipelineTest123"

    def test_10_correlated_payment_captured_produces_recovered(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 10: Correlated payment.captured produces RECOVERED when payment link ID matches."""
        # 1. Pre-seed transaction in RECOVERY_PENDING with active payment link
        txn = Transaction(
            id="txn-uuid-rec-010",
            razorpay_payment_id="pay_OrigFailed010",
            amount=20000,
            status="RECOVERY_PENDING",
            payment_link_id="plink_Correlated010",
        )
        db_session.add(txn)
        db_session.commit()

        worker = WebhookWorker(redis_client=fake_redis, db=db_session)

        # 2. Ingest payment.captured correlated by payment_link_id
        cap_event = _build_captured_event(
            payment_id="pay_CapSuccess010",
            amount=20000,
            payment_link_id="plink_Correlated010",
            notes={"transaction_id": "txn-uuid-rec-010", "recovered_by": "RecoverAI"},
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(cap_event))

        result = worker.pop_and_process()

        assert result["transaction_status"] == "RECOVERED"
        db_session.refresh(txn)
        assert txn.status == "RECOVERED"

    def test_11_unrelated_payment_captured_produces_captured(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 11: Unrelated payment.captured produces CAPTURED, NOT RECOVERED."""
        worker = WebhookWorker(redis_client=fake_redis, db=db_session)

        # Ingest an organic payment with no recovery link or notes
        cap_event = _build_captured_event(
            payment_id="pay_Organic011",
            amount=15000,
            customer_id="cust_Organic011",
            payment_link_id=None,
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(cap_event))

        result = worker.pop_and_process()

        assert result["transaction_status"] == "CAPTURED"
        assert result["transaction_status"] != "RECOVERED"

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Organic011").first()
        assert txn.status == "CAPTURED"
        assert txn.status != "RECOVERED"

    def test_12_delayed_payment_failed_cannot_overwrite_recovered(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 12: Delayed payment.failed arriving after recovery cannot overwrite RECOVERED."""
        # 1. Pre-seed transaction already RECOVERED
        txn = Transaction(
            razorpay_payment_id="pay_Recovered012",
            amount=20000,
            status="RECOVERED",
            payment_link_id="plink_Done012",
        )
        db_session.add(txn)
        db_session.commit()

        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=MockLLMClient()),
        )

        # 2. Delayed payment.failed arrives
        delayed_event = _build_failed_event(payment_id="pay_Recovered012", amount=20000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(delayed_event))

        result = worker.pop_and_process()

        assert result["status"] == "already_terminal"
        db_session.refresh(txn)
        assert txn.status == "RECOVERED"
        assert txn.status != "FAILED"

    def test_13_duplicate_payment_failed_is_idempotent(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 13: Duplicate payment.failed does not trigger duplicate link creation."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.90,
                "rationale": "Create link.",
            })
        )
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Dup013", amount=20000)

        # Process first event
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))
        r1 = worker.pop_and_process()
        assert r1["action_result"]["idempotent"] is False
        assert mock_rzp.call_count == 1

        # Process duplicate event
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))
        r2 = worker.pop_and_process()
        assert r2["idempotent"] is True
        assert mock_rzp.call_count == 1  # No second API call

    def test_14_duplicate_payment_captured_is_idempotent(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 14: Duplicate payment.captured is idempotent and does not alter state."""
        worker = WebhookWorker(redis_client=fake_redis, db=db_session)
        event = _build_captured_event(payment_id="pay_DupCap014", amount=12000)

        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))
        r1 = worker.pop_and_process()
        assert r1["transaction_status"] == "CAPTURED"

        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))
        r2 = worker.pop_and_process()
        assert r2["transaction_status"] == "CAPTURED"

        txns = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_DupCap014").all()
        assert len(txns) == 1

    def test_15_gemini_failure_fails_safely(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 15: Gemini timeout or API error fails safely to STOP without executing recovery."""
        mock_llm = MockLLMClient(exception_to_raise=TimeoutError("Gemini API deadline exceeded"))
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_LlmFail015", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["recovery_decision"]["action"] == "STOP"
        assert result["safety_decision"]["final_action"] == "STOP"
        assert mock_rzp.call_count == 0  # No link created

    def test_16_razorpay_failure_records_failed_execution(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 16: Razorpay API failure records failed execution in audit trail."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.90,
                "rationale": "Approved.",
            })
        )
        mock_rzp = MockRazorpayClient(
            exception_to_raise=RazorpayAPIError(
                message="Razorpay API Error",
                status_code=400,
                error_code="BAD_REQUEST_ERROR",
                error_description="Merchant account suspended in Test Mode",
            )
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_RzpFail016", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["action_result"]["success"] is False
        assert result["action_result"]["error_code"] == "BAD_REQUEST_ERROR"

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_RzpFail016").first()
        assert txn.status != "RECOVERED"
        assert txn.status != "RECOVERY_PENDING"

        # Check audit trail recorded the error
        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()
        assert retry is not None
        assert retry.execution_result == "BAD_REQUEST_ERROR"
        assert "Merchant account suspended" in (retry.error_message or "")

    def test_17_unsupported_retry_never_claims_success(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 17: RETRY action honestly returns ACTION_NOT_SUPPORTED without claiming recovery."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "RETRY",
                "confidence": 0.95,
                "rationale": "Automated retry recommended for transient bank error.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Retry017", amount=5000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["action_result"]["success"] is False
        assert result["action_result"]["error_code"] == "ACTION_NOT_SUPPORTED"

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Retry017").first()
        assert txn.status == "FAILED"
        assert txn.status != "RECOVERED"

    def test_18_unsupported_reminder_never_claims_success(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 18: REMINDER action honestly returns NOT_IMPLEMENTED without claiming recovery."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "REMINDER",
                "confidence": 0.90,
                "rationale": "Send SMS reminder to customer.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Remind018", amount=5000, customer_id="cust_Valid018")
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["action_result"]["success"] is False
        assert result["action_result"]["error_code"] == "NOT_IMPLEMENTED"

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Remind018").first()
        assert txn.status == "FAILED"
        assert txn.status != "RECOVERED"

    def test_19_revenue_at_risk_calculation_is_correct(self, db_session: Session):
        """Test 19: revenue_at_risk is sum of amounts for unrecovered eligible failures."""
        # 1. Eligible FAILED transaction: ₹5,000
        t1 = Transaction(razorpay_payment_id="p1", amount=5000, status="FAILED", failure_category="BANK_TIMEOUT")
        # 2. Eligible RECOVERY_PENDING transaction: ₹15,000
        t2 = Transaction(razorpay_payment_id="p2", amount=15000, status="RECOVERY_PENDING", failure_category="NETWORK_ERROR")
        # 3. Already RECOVERED transaction: ₹20,000 (NOT at risk)
        t3 = Transaction(razorpay_payment_id="p3", amount=20000, status="RECOVERED", failure_category="BANK_TIMEOUT")
        # 4. Ineligible FRAUD transaction: ₹50,000 (NOT at risk)
        t4 = Transaction(razorpay_payment_id="p4", amount=50000, status="FAILED", failure_category="FRAUD_RISK")
        # 5. STOPPED transaction: ₹8,000 (NOT at risk)
        t5 = Transaction(razorpay_payment_id="p5", amount=8000, status="STOPPED", failure_category="CARD_DECLINED")

        db_session.add_all([t1, t2, t3, t4, t5])
        db_session.commit()

        metrics = RecoveryMetricsService(db_session).calculate_metrics()
        # revenue_at_risk = 5000 + 15000 = 20000
        assert metrics.revenue_at_risk == 20000

    def test_20_recovered_revenue_calculation_is_correct(self, db_session: Session):
        """Test 20: recovered_revenue is sum of amounts for transactions in RECOVERED state."""
        t1 = Transaction(razorpay_payment_id="r1", amount=20000, status="RECOVERED")
        t2 = Transaction(razorpay_payment_id="r2", amount=35000, status="RECOVERED")
        t3 = Transaction(razorpay_payment_id="r3", amount=10000, status="FAILED")
        t4 = Transaction(razorpay_payment_id="r4", amount=50000, status="CAPTURED")  # organic

        db_session.add_all([t1, t2, t3, t4])
        db_session.commit()

        metrics = RecoveryMetricsService(db_session).calculate_metrics()
        # recovered_revenue = 20000 + 35000 = 55000
        assert metrics.recovered_revenue == 55000
        assert metrics.total_recovered_transactions == 2

    def test_21_recovery_rate_calculation_is_correct(self, db_session: Session):
        """Test 21: recovery_rate strictly equals total_recovered_transactions / eligible_failed_transactions."""
        # 2 recovered transactions
        t1 = Transaction(razorpay_payment_id="t1", amount=10000, status="RECOVERED", failure_category="BANK_TIMEOUT")
        t2 = Transaction(razorpay_payment_id="t2", amount=10000, status="RECOVERED", failure_category="PAYMENT_TIMEOUT")
        # 1 pending recovery
        t3 = Transaction(razorpay_payment_id="t3", amount=10000, status="RECOVERY_PENDING", failure_category="BANK_TIMEOUT")
        # 1 failed
        t4 = Transaction(razorpay_payment_id="t4", amount=10000, status="FAILED", failure_category="NETWORK_ERROR")
        # Total eligible failed transactions = 4. Recovered = 2. Rate = 2/4 = 0.50
        db_session.add_all([t1, t2, t3, t4])
        db_session.commit()

        metrics = RecoveryMetricsService(db_session).calculate_metrics()
        assert metrics.total_recovered_transactions == 2
        assert metrics.eligible_failed_transactions == 4
        assert metrics.recovery_rate == 0.5

    def test_22_zero_denominator_recovery_rate_handled(self, db_session: Session):
        """Test 22: Zero-denominator recovery rate returns 0.0 without ZeroDivisionError."""
        # Clean empty database
        metrics = RecoveryMetricsService(db_session).calculate_metrics()
        assert metrics.recovery_rate == 0.0
        assert metrics.total_recovered_transactions == 0
        assert metrics.eligible_failed_transactions == 0

    def test_23_audit_trail_contains_ai_recommendation(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 23: Audit trail contains AI recommendation, confidence, and rationale."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.89,
                "rationale": "High conversion potential on UPI link.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Audit023", amount=12000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Audit023").first()
        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()

        assert retry is not None
        assert retry.recommended_action == "PAYMENT_LINK"
        assert retry.confidence == 0.89
        assert "High conversion potential" in (retry.ai_rationale or "")

    def test_24_audit_trail_contains_safety_guard_decision(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 24: Audit trail contains Safety Guard decision and rule ID."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.85,
                "rationale": "Eligible.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Audit024", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Audit024").first()
        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()

        assert retry is not None
        assert retry.safety_decision == "APPROVE"
        assert retry.safety_rule_id == "APPROVED"

    def test_25_audit_trail_contains_final_action(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 25: Audit trail contains final action authorized by Safety Guard."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.85,
                "rationale": "Eligible.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Audit025", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Audit025").first()
        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()

        assert retry is not None
        assert retry.final_action == "PAYMENT_LINK"

    def test_26_audit_trail_contains_execution_outcome(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 26: Audit trail contains execution result, external ID, and outcome."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.85,
                "rationale": "Eligible.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Audit026", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Audit026").first()
        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()

        assert retry is not None
        assert retry.execution_result == "SUCCESS"
        assert retry.result == "LINK_CREATED"
        assert retry.external_id == "plink_PipelineTest123"

    def test_27_no_api_secrets_appear_in_persisted_audit_data(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 27: No API secrets, CVVs, or sensitive credentials appear in database audit records."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.90,
                "rationale": "Payment link with standard parameters.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Secret027", amount=10000)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Secret027").first()
        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()

        all_text = f"{retry.ai_rationale} {retry.error_message} {retry.action} {txn.failure_description}"
        # Assert no common secret patterns are present
        assert "AIzaSy" not in all_text
        assert "mock_secret_test" not in all_text
        assert "cvv" not in all_text.lower()
        assert "password" not in all_text.lower()

    def test_28_repeated_processing_produces_deterministic_outcome(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test 28: Repeated processing of the same event produces identical deterministic state."""
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.90,
                "rationale": "Deterministic test recommendation.",
            })
        )
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(payment_id="pay_Det028", amount=20000)

        # Run 1
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))
        worker.pop_and_process()

        txn1 = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Det028").first()
        status1 = txn1.status
        link1 = txn1.payment_link_id

        # Run 2 (repeated event)
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))
        worker.pop_and_process()

        db_session.refresh(txn1)
        assert txn1.status == status1
        assert txn1.payment_link_id == link1
        assert mock_rzp.call_count == 1  # Exactly 1 call, idempotent on repeat


class TestDemoScenarios:
    """Test suite for the 4 core Demo Scenarios specified in Phase 7."""

    def test_scenario_1_successful_recovery_retry_unsupported(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """SCENARIO 1 — RETRY recovery recommended, approved, honestly recorded as unsupported.

        Amount: ₹5,000 (500000 paise)
        Failure: temporary BANK_TIMEOUT
        Gemini: RETRY
        Safety Guard: APPROVE / RETRY
        Action Executor: ACTION_NOT_SUPPORTED
        Transaction: FAILED (honestly recorded without claiming recovery)
        """
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "RETRY",
                "confidence": 0.95,
                "rationale": "Temporary bank timeout; automated retry recommended.",
            })
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=MockRazorpayClient(), db=db_session),
        )

        event = _build_failed_event(
            payment_id="pay_Scenario1_001",
            amount=500000,
            error_code="BAD_REQUEST_ERROR",
            error_description="Bank timed out while confirming UPI PIN.",
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["recovery_decision"]["action"] == "RETRY"
        assert result["safety_decision"]["decision"] == "APPROVE"
        assert result["safety_decision"]["final_action"] == "RETRY"
        assert result["action_result"]["success"] is False
        assert result["action_result"]["error_code"] == "ACTION_NOT_SUPPORTED"

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Scenario1_001").first()
        assert txn.status == "FAILED"
        assert txn.status != "RECOVERED"

        retry = db_session.query(RetryHistory).filter_by(transaction_id=txn.id).first()
        assert retry.execution_result == "ACTION_NOT_SUPPORTED"

    def test_scenario_2_payment_link_recovery(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """SCENARIO 2 — PAYMENT LINK RECOVERY.

        Amount: ₹20,000 (2000000 paise)
        Failure: eligible recovery failure
        Gemini: PAYMENT_LINK
        Safety Guard: APPROVE / PAYMENT_LINK
        Action Executor: creates Razorpay Test Mode Payment Link
        Transaction: RECOVERY_PENDING
        After correlated payment.captured: RECOVERED
        Recovered revenue: ₹20,000
        """
        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.92,
                "rationale": "Eligible for customer re-attempt via payment link.",
            })
        )
        mock_rzp = MockRazorpayClient(
            response_data={
                "id": "plink_Scenario2_123",
                "short_url": "https://rzp.io/i/Scenario2_123",
                "status": "created",
                "amount": 2000000,
                "currency": "INR",
            }
        )
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        # 1. Ingest failed payment
        fail_event = _build_failed_event(
            payment_id="pay_Scenario2_002",
            amount=2000000,
            error_code="BAD_REQUEST_ERROR",
            error_description="Bank timed out waiting for authorization.",
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(fail_event))
        worker.pop_and_process()

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Scenario2_002").first()
        assert txn.status == "RECOVERY_PENDING"
        assert txn.payment_link_id == "plink_Scenario2_123"

        # 2. Customer pays via the link -> payment.captured
        cap_event = _build_captured_event(
            payment_id="pay_Scenario2_Cap002",
            amount=2000000,
            payment_link_id="plink_Scenario2_123",
            notes={"transaction_id": txn.id, "recovered_by": "RecoverAI"},
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(cap_event))
        worker.pop_and_process()

        db_session.refresh(txn)
        assert txn.status == "RECOVERED"

        # 3. Verify metrics
        metrics = RecoveryMetricsService(db_session).calculate_metrics()
        assert metrics.recovered_revenue == 2000000
        assert metrics.total_recovered_transactions == 1

    def test_scenario_3_unsafe_recovery(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """SCENARIO 3 — UNSAFE RECOVERY.

        High-risk/fraud/blocking flag
        Gemini: PAYMENT_LINK or RETRY
        Safety Guard: OVERRIDE / STOP
        Action Executor: NO external call
        Transaction: STOPPED
        """
        # Pre-seed active risk flag on customer
        flag = RiskFlag(customer_id="cust_Fraudster003", flag="FRAUD_SUSPICION", active=True)
        db_session.add(flag)
        db_session.commit()

        mock_llm = MockLLMClient(
            response_text=json.dumps({
                "action": "PAYMENT_LINK",
                "confidence": 0.95,
                "rationale": "Try sending link.",
            })
        )
        mock_rzp = MockRazorpayClient()
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            decision_engine=DecisionEngine(llm_client=mock_llm),
            action_executor=ActionExecutor(razorpay_client=mock_rzp, db=db_session),
        )

        event = _build_failed_event(
            payment_id="pay_Scenario3_003",
            amount=10000,
            customer_id="cust_Fraudster003",
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event))

        result = worker.pop_and_process()

        assert result["status"] == "ineligible_stopped"
        assert result["transaction_status"] == "STOPPED"
        assert mock_rzp.call_count == 0  # NO external call

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Scenario3_003").first()
        assert txn.status == "STOPPED"

    def test_scenario_4_organic_success(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """SCENARIO 4 — ORGANIC SUCCESS.

        A normal successful payment unrelated to RecoverAI:
        payment.captured
        Result: CAPTURED (NOT RECOVERED)
        """
        worker = WebhookWorker(redis_client=fake_redis, db=db_session)

        cap_event = _build_captured_event(
            payment_id="pay_Scenario4_004",
            amount=50000,
            customer_id="cust_Organic004",
            payment_link_id=None,
        )
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(cap_event))

        result = worker.pop_and_process()

        assert result["transaction_status"] == "CAPTURED"
        assert result["transaction_status"] != "RECOVERED"

        txn = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_Scenario4_004").first()
        assert txn.status == "CAPTURED"
        assert txn.status != "RECOVERED"


class TestMetricsEndpoint:
    """Test suite for the internal metrics API endpoints."""

    def test_metrics_api_root_and_v1(self, client):
        """Verify GET /metrics/recovery and GET /api/v1/metrics/recovery return 200."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from sqlalchemy.pool import StaticPool
        from app.models.base import Base
        from app.core.database import get_db
        from app.main import app

        test_engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(bind=test_engine)
        TestingSessionLocal = sessionmaker(bind=test_engine)

        def override_get_db():
            session = TestingSessionLocal()
            try:
                yield session
            finally:
                session.close()

        app.dependency_overrides[get_db] = override_get_db
        try:
            # 1. Root-mounted metrics endpoint
            resp1 = client.get("/metrics/recovery")
            assert resp1.status_code == 200
            data1 = resp1.json()
            assert "revenue_at_risk" in data1
            assert "recovered_revenue" in data1
            assert "recovery_rate" in data1
            assert "total_failed_transactions" in data1
            assert "total_recovered_transactions" in data1
            assert "payment_links_created" in data1
            assert "stopped_transactions" in data1

            # 2. V1-prefixed metrics endpoint
            resp2 = client.get("/api/v1/metrics/recovery")
            assert resp2.status_code == 200
            data2 = resp2.json()
            assert data2 == data1
        finally:
            app.dependency_overrides.pop(get_db, None)


