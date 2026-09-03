"""Tests for Payment Analysis Service and Normalized Output Schema.

Covers:
L. Malformed webhook analysis input
- Validation of PaymentAnalysis output schema
- Recovery eligibility and context calculation
- Database persistence of failed transactions
"""

import pytest
from sqlalchemy.orm import Session

from app.models.transaction import Transaction
from app.repositories.customer_repository import CustomerRepository
from app.schemas.analysis import PaymentAnalysis
from app.services.analysis_service import AnalysisService


class TestAnalysisService:
    """Test suite for payment failure analysis."""

    def test_l_malformed_webhook_analysis_input(self, db_session: Session):
        """Test L: Malformed webhook inputs raise clear ValueError without crashing."""
        service = AnalysisService(db=db_session)

        # 1. Empty dictionary
        with pytest.raises(ValueError, match="Invalid event data|Could not extract payment"):
            service.analyze_payment_failure({})

        # 2. None input
        with pytest.raises(ValueError, match="Invalid event data"):
            service.analyze_payment_failure(None)  # type: ignore

        # 3. Payload missing payment entity
        with pytest.raises(ValueError, match="Could not extract payment entity"):
            service.analyze_payment_failure({"payload": {"order": {"entity": {}}}})

        # 4. Payment entity missing required 'id'
        with pytest.raises(ValueError, match="missing required 'id'"):
            service.analyze_payment_failure({
                "payload": {
                    "payment": {
                        "entity": {
                            "amount": 50000,
                            "currency": "INR",
                        }
                    }
                }
            })

        # 5. Payment entity missing required 'amount'
        with pytest.raises(ValueError, match="missing required 'amount'"):
            service.analyze_payment_failure({
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_MissingAmount001",
                            "currency": "INR",
                        }
                    }
                }
            })

        # 6. Payment entity with non-integer amount
        with pytest.raises(ValueError, match="Invalid amount value"):
            service.analyze_payment_failure({
                "payload": {
                    "payment": {
                        "entity": {
                            "id": "pay_InvalidAmount002",
                            "amount": "not_a_number",
                        }
                    }
                }
            })

    def test_valid_payment_failed_analysis_schema(self, db_session: Session):
        """Test valid payment failure produces fully populated PaymentAnalysis schema."""
        service = AnalysisService(db=db_session)

        event = {
            "entity": "event",
            "event": "payment.failed",
            "account_id": "acc_TestMerchant001",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_NormalFail001",
                        "order_id": "order_Order001",
                        "amount": 8999,
                        "currency": "INR",
                        "status": "failed",
                        "method": "card",
                        "customer_id": "cust_KnownUser001",
                        "error_code": "GATEWAY_ERROR",
                        "error_description": "Temporary network error between bank gateway.",
                        "error_source": "gateway",
                        "error_step": "payment_authorization",
                        "error_reason": "network_error",
                    }
                }
            },
            "created_at": 1700000000,
        }

        analysis = service.analyze_payment_failure(event)

        # Verify instance and fields
        assert isinstance(analysis, PaymentAnalysis)
        assert analysis.razorpay_payment_id == "pay_NormalFail001"
        assert analysis.razorpay_order_id == "order_Order001"
        assert analysis.customer_id == "cust_KnownUser001"
        assert analysis.amount == 8999
        assert analysis.currency == "INR"
        assert analysis.payment_method == "card"
        assert analysis.failure_category == "NETWORK_ERROR"
        assert analysis.failure_code == "GATEWAY_ERROR"
        assert "network error" in (analysis.failure_description or "").lower()

        # Verify recovery context
        assert analysis.recovery_context["eligible_for_analysis"] is True
        assert analysis.recovery_context["is_already_captured"] is False
        assert analysis.recovery_context["is_already_recovered"] is False
        assert analysis.recovery_context["is_transient_failure"] is True
        assert analysis.recovery_context["requires_step_up_auth"] is False

        # Verify persisted in database
        saved = db_session.query(Transaction).filter_by(razorpay_payment_id="pay_NormalFail001").first()
        assert saved is not None
        assert saved.id == analysis.transaction_id
        assert saved.status == "FAILED"
        assert saved.failure_category == "NETWORK_ERROR"

    def test_fraud_failure_marks_not_eligible(self, db_session: Session):
        """Test failure classified as FRAUD_RISK is marked ineligible for automated recovery."""
        service = AnalysisService(db=db_session)

        event = {
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_FraudRisk001",
                        "amount": 150000,
                        "currency": "INR",
                        "status": "failed",
                        "error_step": "payment_risk",
                        "error_reason": "risk_threshold_exceeded",
                        "error_description": "Transaction rejected by fraud risk engine.",
                    }
                }
            }
        }

        analysis = service.analyze_payment_failure(event)
        assert analysis.failure_category == "FRAUD_RISK"
        assert analysis.recovery_context["eligible_for_analysis"] is False

    def test_customer_with_blocking_risk_flag_ineligible(self, db_session: Session):
        """Test customer with active blocking risk flag is marked ineligible for recovery."""
        repo = CustomerRepository(db_session)
        cust_id = "cust_Blacklisted001"
        repo.add_risk_flag(cust_id, "BLACKLISTED", active=True)

        service = AnalysisService(db=db_session)

        event = {
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_BlockedUser001",
                        "customer_id": cust_id,
                        "amount": 25000,
                        "currency": "INR",
                        "status": "failed",
                        "error_code": "BAD_REQUEST_ERROR",
                        "error_description": "Insufficient funds in account",
                        "error_reason": "insufficient_funds",
                    }
                }
            }
        }

        analysis = service.analyze_payment_failure(event)
        assert analysis.failure_category == "INSUFFICIENT_FUNDS"
        assert "BLACKLISTED" in analysis.active_risk_flags
        # Ineligible due to blocking risk flag
        assert analysis.recovery_context["eligible_for_analysis"] is False
        assert analysis.recovery_context["has_active_risk_flags"] is True

    def test_already_captured_transaction_marked_ineligible(self, db_session: Session):
        """Test transaction already marked CAPTURED is marked ineligible for recovery."""
        repo = CustomerRepository(db_session)
        # Pre-seed captured transaction
        repo.mark_transaction_captured(
            razorpay_payment_id="pay_AlreadyCaptured001",
            amount=50000,
            currency="INR",
        )

        service = AnalysisService(db=db_session)
        event = {
            "payload": {
                "payment": {
                    "entity": {
                        "id": "pay_AlreadyCaptured001",
                        "amount": 50000,
                        "currency": "INR",
                        "status": "failed",
                        "error_code": "GATEWAY_ERROR",
                        "error_description": "Delayed network error arrived after capture",
                        "error_reason": "network_error",
                    }
                }
            }
        }

        analysis = service.analyze_payment_failure(event)
        assert analysis.recovery_context["is_already_captured"] is True
        assert analysis.recovery_context["eligible_for_analysis"] is False

        # Verify DB status remained CAPTURED, not overwritten back to FAILED
        db_txn = repo.get_transaction_by_payment_id("pay_AlreadyCaptured001")
        assert db_txn is not None
        assert db_txn.status == "CAPTURED"
