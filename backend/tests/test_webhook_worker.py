"""Tests for Redis Webhook Worker.

Covers:
M. Worker successfully consumes a payment.failed event from Redis queue
N. Worker does not invoke recovery logic for payment.captured
O. Database persistence works through test database dependencies
- Resilience against malformed messages, corrupt JSON, and non-dict inputs
- Preservation of transaction recovery lifecycle states
"""

import json
from sqlalchemy.orm import Session

from app.core.queue import WEBHOOK_QUEUE_NAME
from app.models.retry_history import RetryHistory
from app.models.risk_flag import RiskFlag
from app.models.transaction import Transaction
from app.workers.webhook_worker import WebhookWorker
from tests.conftest import FakeRedis


class TestWebhookWorker:
    """Test suite for WebhookWorker Redis consumer."""

    def test_m_worker_consumes_payment_failed_event(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test M: Worker successfully pops payment.failed from Redis and runs analysis."""
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            queue_name=WEBHOOK_QUEUE_NAME,
        )

        event_data = {
            "event_id": "evt_TestFailed001",
            "event_type": "payment.failed",
            "account_id": "acc_TestMerchant001",
            "payload": {
                "entity": "event",
                "event": "payment.failed",
                "account_id": "acc_TestMerchant001",
                "contains": ["payment"],
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_WorkerFail001",
                            "order_id": "order_WorkerOrder001",
                            "amount": 4999,
                            "currency": "INR",
                            "status": "failed",
                            "method": "upi",
                            "customer_id": "cust_WorkerUser001",
                            "error_code": "BAD_REQUEST_ERROR",
                            "error_description": "Bank timed out while confirming UPI PIN.",
                            "error_source": "bank",
                            "error_step": "payment_authorization",
                            "error_reason": "bank_timed_out",
                        }
                    }
                },
                "created_at": 1700000000,
            },
        }

        # Push to fake redis queue
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(event_data))
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 1

        # Process one item
        result = worker.pop_and_process()

        assert result is not None
        assert result["status"] == "analyzed"
        assert result["event_type"] == "payment.failed"
        assert result["event_id"] == "evt_TestFailed001"

        analysis = result["analysis"]
        assert analysis["razorpay_payment_id"] == "pay_WorkerFail001"
        assert analysis["failure_category"] == "BANK_TIMEOUT"
        assert analysis["amount"] == 4999
        assert analysis["recovery_context"]["eligible_for_analysis"] is True

        # Confirm queue is now empty
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 0

        # Confirm database has the transaction
        txn = (
            db_session.query(Transaction)
            .filter_by(razorpay_payment_id="pay_WorkerFail001")
            .first()
        )
        assert txn is not None
        assert txn.status == "FAILED"
        assert txn.failure_category == "BANK_TIMEOUT"

    def test_n_worker_processes_payment_captured_without_recovery(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Test N: Worker acknowledges payment.captured without invoking recovery analysis."""
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            queue_name=WEBHOOK_QUEUE_NAME,
        )

        # 1. Pre-seed an existing failed transaction
        seed_txn = Transaction(
            razorpay_payment_id="pay_SeedPayment001",
            razorpay_order_id="order_SeedOrder001",
            customer_id="cust_Seed001",
            amount=75000,
            status="FAILED",
            failure_category="INSUFFICIENT_FUNDS",
        )
        db_session.add(seed_txn)
        db_session.commit()

        captured_event = {
            "event_id": "evt_Captured001",
            "event_type": "payment.captured",
            "payload": {
                "entity": "event",
                "event": "payment.captured",
                "account_id": "acc_TestMerchant001",
                "contains": ["payment"],
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_SeedPayment001",
                            "order_id": "order_SeedOrder001",
                            "amount": 75000,
                            "currency": "INR",
                            "status": "captured",
                            "method": "card",
                            "customer_id": "cust_Seed001",
                        }
                    }
                },
                "created_at": 1700000500,
            },
        }

        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(captured_event))

        # Process the event
        result = worker.pop_and_process()

        assert result is not None
        assert result["status"] == "acknowledged"
        assert result["event_type"] == "payment.captured"
        assert result["recovery_triggered"] is False
        assert result["payment_id"] == "pay_SeedPayment001"
        assert result["transaction_status"] == "CAPTURED"

        # Verify transaction status transitioned to CAPTURED (NOT RECOVERED)
        # Outcome Tracker in later phases will determine causality before setting RECOVERED
        db_session.refresh(seed_txn)
        assert seed_txn.status == "CAPTURED"
        assert seed_txn.status != "RECOVERED"

    def test_o_database_persistence_and_relationships(self, db_session: Session):
        """Test O: Verifies database persistence, foreign keys, and relationships work."""
        # 1. Create a Transaction
        txn = Transaction(
            razorpay_payment_id="pay_RelationshipTest001",
            razorpay_order_id="order_Rel001",
            customer_id="cust_Rel001",
            amount=9900,
            status="RECOVERY_PENDING",
            failure_category="CARD_DECLINED",
        )
        db_session.add(txn)
        db_session.commit()
        db_session.refresh(txn)

        # 2. Add RetryHistory record linked to this transaction
        retry = RetryHistory(
            transaction_id=txn.id,
            attempt_number=1,
            action="smart_retry",
            result="PENDING",
        )
        db_session.add(retry)
        db_session.commit()

        # 3. Add RiskFlag
        flag = RiskFlag(
            customer_id="cust_Rel001",
            flag="VELOCITY_EXCEEDED",
            active=True,
        )
        db_session.add(flag)
        db_session.commit()

        # Query back and verify relationships
        queried_txn = (
            db_session.query(Transaction)
            .filter_by(razorpay_payment_id="pay_RelationshipTest001")
            .first()
        )
        assert queried_txn is not None
        assert len(queried_txn.retry_history) == 1
        assert queried_txn.retry_history[0].action == "smart_retry"
        assert queried_txn.retry_history[0].transaction.id == txn.id

        # Verify risk flag
        queried_flag = (
            db_session.query(RiskFlag)
            .filter_by(customer_id="cust_Rel001")
            .first()
        )
        assert queried_flag is not None
        assert queried_flag.flag == "VELOCITY_EXCEEDED"
        assert queried_flag.active is True

    def test_worker_resilience_against_malformed_messages(
        self,
        fake_redis: FakeRedis,
        db_session: Session,
    ):
        """Verify worker safely handles corrupt data without crashing."""
        worker = WebhookWorker(
            redis_client=fake_redis,
            db=db_session,
            queue_name=WEBHOOK_QUEUE_NAME,
        )

        # 1. Non-JSON string
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, "THIS IS NOT JSON {{{")
        r1 = worker.pop_and_process()
        assert r1["status"] == "malformed_json"

        # 2. JSON that is a list instead of object
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps(["some", "list"]))
        r2 = worker.pop_and_process()
        assert r2["status"] == "error"

        # 3. JSON object missing event_type
        fake_redis.lpush(WEBHOOK_QUEUE_NAME, json.dumps({"foo": "bar"}))
        r3 = worker.pop_and_process()
        assert r3["status"] == "missing_event_type"

        # 4. None / empty queue
        r4 = worker.pop_and_process()
        assert r4 is None

        # 5. Worker run loop terminates cleanly with max_iterations
        iterations = worker.run(max_iterations=3, poll_interval_seconds=0.01)
        assert iterations == 0  # 0 events in empty queue
