"""Tests for Customer Context and Customer Repository.

Covers:
H. Customer with 0 previous attempts
I. Customer with multiple attempts in 24h
J. Customer with active risk flag
Safe customer ID extraction from official Razorpay fields.
"""

from datetime import datetime, timedelta, timezone
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.repositories.customer_repository import CustomerRepository


class TestCustomerContext:
    """Test suite for customer context and history retrieval."""

    def test_h_customer_with_zero_previous_attempts(self, db_session: Session):
        """Test H: Customer with 0 previous attempts returns clear zeroed context."""
        repo = CustomerRepository(db_session)
        history = repo.get_customer_history("cust_NewUser001")

        assert history.customer_id == "cust_NewUser001"
        assert history.total_attempts == 0
        assert history.attempt_count_24h == 0
        assert history.previous_successful_payments == 0
        assert history.previous_failed_payments == 0
        assert history.active_risk_flags == []

    def test_h_none_customer_id_handled_safely(self, db_session: Session):
        """Test H: Safe handling when no customer_id is available."""
        repo = CustomerRepository(db_session)
        history = repo.get_customer_history(None)

        assert history.customer_id is None
        assert history.total_attempts == 0
        assert history.attempt_count_24h == 0
        assert history.active_risk_flags == []

    def test_i_customer_with_multiple_attempts_in_24h(self, db_session: Session):
        """Test I: Accurately counts attempts in the last 24 hours vs older attempts."""
        repo = CustomerRepository(db_session)
        cust_id = "cust_ActiveUser002"
        now = datetime.now(timezone.utc)

        # 1. Recent failed transaction (2 hours ago)
        tx1 = Transaction(
            razorpay_payment_id="pay_recent_fail_1",
            customer_id=cust_id,
            amount=50000,
            status="FAILED",
            created_at=now - timedelta(hours=2),
        )
        # 2. Recent failed transaction (10 hours ago)
        tx2 = Transaction(
            razorpay_payment_id="pay_recent_fail_2",
            customer_id=cust_id,
            amount=50000,
            status="FAILED",
            created_at=now - timedelta(hours=10),
        )
        # 3. Recent captured transaction (18 hours ago - Razorpay capture without AI intervention)
        tx3 = Transaction(
            razorpay_payment_id="pay_recent_success_1",
            customer_id=cust_id,
            amount=50000,
            status="CAPTURED",
            created_at=now - timedelta(hours=18),
        )
        # 4. Old transaction from 3 days ago (> 24h)
        tx4 = Transaction(
            razorpay_payment_id="pay_old_fail_1",
            customer_id=cust_id,
            amount=50000,
            status="FAILED",
            created_at=now - timedelta(days=3),
        )
        # 5. Old AI-recovered transaction from 10 days ago (> 24h)
        tx5 = Transaction(
            razorpay_payment_id="pay_old_success_1",
            customer_id=cust_id,
            amount=50000,
            status="RECOVERED",
            created_at=now - timedelta(days=10),
        )

        db_session.add_all([tx1, tx2, tx3, tx4, tx5])
        db_session.commit()

        # Query history for cust_id
        history = repo.get_customer_history(cust_id)

        assert history.customer_id == cust_id
        assert history.total_attempts == 5
        assert history.attempt_count_24h == 3  # tx1, tx2, tx3
        assert history.previous_successful_payments == 2  # tx3 (CAPTURED) + tx5 (RECOVERED)
        assert history.previous_recovered_payments == 1  # only tx5 was specifically AI-recovered
        assert history.previous_failed_payments == 3  # tx1, tx2, tx4

    def test_j_customer_with_active_risk_flag(self, db_session: Session):
        """Test J: Active risk flags are surfaced while inactive flags are excluded."""
        repo = CustomerRepository(db_session)
        cust_id = "cust_RiskyUser003"

        # Add active risk flag
        repo.add_risk_flag(cust_id, "FRAUD_SUSPICION", active=True)
        # Add another active risk flag
        repo.add_risk_flag(cust_id, "CHARGEBACK_HISTORY", active=True)
        # Add inactive risk flag
        repo.add_risk_flag(cust_id, "OLD_RESOLVED_FLAG", active=False)

        history = repo.get_customer_history(cust_id)

        assert "FRAUD_SUSPICION" in history.active_risk_flags
        assert "CHARGEBACK_HISTORY" in history.active_risk_flags
        assert "OLD_RESOLVED_FLAG" not in history.active_risk_flags
        assert len(history.active_risk_flags) == 2

    def test_customer_id_extraction_safely(self):
        """Test safe customer extraction from different Razorpay payload structures."""
        # 1. Standard official customer_id field
        p1 = {"customer_id": "cust_Official123", "amount": 1000}
        assert CustomerRepository.extract_customer_id(p1) == "cust_Official123"

        # 2. Customer ID inside notes
        p2 = {"notes": {"customer_id": "cust_FromNotes456"}, "amount": 2000}
        assert CustomerRepository.extract_customer_id(p2) == "cust_FromNotes456"

        # 3. Customer ID as cust_id inside notes
        p3 = {"notes": {"cust_id": "cust_ShortId789"}, "amount": 3000}
        assert CustomerRepository.extract_customer_id(p3) == "cust_ShortId789"

        # 4. Fallback to email
        p4 = {"email": "shopper@example.com", "amount": 4000}
        assert CustomerRepository.extract_customer_id(p4) == "shopper@example.com"

        # 5. Fallback to contact phone
        p5 = {"contact": "+919876543210", "amount": 5000}
        assert CustomerRepository.extract_customer_id(p5) == "+919876543210"

        # 6. Anonymous / no identity present
        p6 = {"amount": 6000, "notes": {"order_ref": "ref_111"}}
        assert CustomerRepository.extract_customer_id(p6) is None

        # 7. Demo fallback permitted
        p7 = {"amount": 7000, "notes": {"demo_customer_id": "cust_demo_999"}}
        assert CustomerRepository.extract_customer_id(p7, allow_demo_fallback=True) == "cust_demo_999"
