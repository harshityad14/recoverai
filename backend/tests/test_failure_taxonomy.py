"""Tests for Failure Taxonomy and Deterministic Failure Classifier.

Covers:
A. Network error → NETWORK_ERROR
B. Bank timeout → BANK_TIMEOUT
C. Insufficient funds → INSUFFICIENT_FUNDS
D. Card declined → CARD_DECLINED
E. 3DS/authentication failure → THREE_DS_FAILURE / AUTHENTICATION_FAILURE
F. Fraud/risk signal → FRAUD_RISK
G. Unknown failure → UNKNOWN
K. Missing optional Razorpay fields
"""

import pytest
from app.schemas.taxonomy import FailureCategory
from app.services.failure_classifier import FailureClassifier


class TestFailureClassifier:
    """Test suite for deterministic failure classification."""

    def test_a_network_error_classification(self):
        """Test A: Gateway/network failure maps to NETWORK_ERROR."""
        # Case 1: error_code is GATEWAY_ERROR with network description
        result = FailureClassifier.classify(
            error_code="GATEWAY_ERROR",
            error_description="Payment failed due to a temporary network issue. Please retry.",
            error_source="gateway",
            error_step="payment_authorization",
            error_reason="network_error",
        )
        assert result == FailureCategory.NETWORK_ERROR

        # Case 2: Connection reset description with gateway error code
        result2 = FailureClassifier.classify(
            error_code="GATEWAY_ERROR",
            error_description="Connection reset by peer while connecting to processor.",
            error_source="gateway",
        )
        assert result2 == FailureCategory.NETWORK_ERROR

    def test_b_bank_timeout_classification(self):
        """Test B: Bank or issuing gateway timeout maps to BANK_TIMEOUT."""
        # Case 1: Explicit bank_timed_out reason
        result = FailureClassifier.classify(
            error_code="GATEWAY_ERROR",
            error_description="The issuing bank did not respond in time.",
            error_source="bank",
            error_step="payment_authorization",
            error_reason="bank_timed_out",
        )
        assert result == FailureCategory.BANK_TIMEOUT

        # Case 2: Bank source with timeout keyword in description
        result2 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Bank server timeout during transaction processing",
            error_source="bank",
            error_step="payment_authorization",
        )
        assert result2 == FailureCategory.BANK_TIMEOUT

    def test_c_insufficient_funds_classification(self):
        """Test C: Insufficient funds maps to INSUFFICIENT_FUNDS."""
        # Case 1: error_reason is insufficient_funds
        result = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Payment declined due to insufficient funds in customer account.",
            error_source="customer",
            error_step="payment_authorization",
            error_reason="insufficient_funds",
        )
        assert result == FailureCategory.INSUFFICIENT_FUNDS

        # Case 2: Description indicates low balance
        result2 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Account has insufficient balance for transaction.",
            error_source="bank",
        )
        assert result2 == FailureCategory.INSUFFICIENT_FUNDS

    def test_d_card_declined_classification(self):
        """Test D: Card decline reasons map to CARD_DECLINED."""
        # Case 1: Explicit card_declined reason
        result = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="The card was declined by the issuing bank.",
            error_source="bank",
            error_step="payment_authorization",
            error_reason="card_declined",
        )
        assert result == FailureCategory.CARD_DECLINED

        # Case 2: Card expired
        result2 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="The card has expired. Please use a valid card.",
            error_source="customer",
            error_reason="card_expired",
        )
        assert result2 == FailureCategory.CARD_DECLINED

        # Case 3: Do not honor
        result3 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Bank declined with code: do not honor.",
            error_source="bank",
            error_reason="do_not_honor",
        )
        assert result3 == FailureCategory.CARD_DECLINED

    def test_e_3ds_and_authentication_failure_classification(self):
        """Test E: 3DS/OTP and authentication failures map to appropriate taxonomy."""
        # 3DS / OTP failure
        result_3ds = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Incorrect OTP was entered by the user.",
            error_source="customer",
            error_step="payment_authentication",
            error_reason="invalid_otp",
        )
        assert result_3ds == FailureCategory.THREE_DS_FAILURE

        result_3ds_2 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="3D Secure authentication failed at issuer portal.",
            error_source="customer",
            error_step="payment_authentication",
            error_reason="3ds_failed",
        )
        assert result_3ds_2 == FailureCategory.THREE_DS_FAILURE

        # General Authentication Failure (MPIN, PIN, credentials)
        result_auth = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="The UPI PIN is incorrect.",
            error_source="customer",
            error_step="payment_authentication",
            error_reason="pin_incorrect",
        )
        assert result_auth == FailureCategory.AUTHENTICATION_FAILURE

    def test_f_fraud_risk_classification(self):
        """Test F: Fraud or risk signals map to FRAUD_RISK with highest priority."""
        # Case 1: error_step is payment_risk
        result = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Transaction blocked by risk assessment engine.",
            error_source="business",
            error_step="payment_risk",
            error_reason="risk_threshold_exceeded",
        )
        assert result == FailureCategory.FRAUD_RISK

        # Case 2: Fraud suspicion keyword
        result2 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Suspicious transaction flagged for security review.",
            error_source="customer",
            error_reason="suspicious",
        )
        assert result2 == FailureCategory.FRAUD_RISK

        # Case 3: Blacklisted entity
        result3 = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Card is blacklisted due to prior chargeback activity.",
            error_reason="card_blacklisted",
        )
        assert result3 == FailureCategory.FRAUD_RISK

    def test_g_unknown_failure_classification(self):
        """Test G: Unclassifiable or ambiguous errors map to UNKNOWN."""
        # Case 1: Completely uninformative generic error
        result = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Payment failed.",
            error_source="customer",
            error_step="payment_initiation",
            error_reason="payment_failed",
        )
        assert result == FailureCategory.UNKNOWN

        # Case 2: Empty inputs
        result2 = FailureClassifier.classify()
        assert result2 == FailureCategory.UNKNOWN

        # Case 3: Arbitrary unmapped message
        result3 = FailureClassifier.classify(
            error_code="SOME_CUSTOM_ERROR",
            error_description="Something unpredictable happened with merchant catalog.",
        )
        assert result3 == FailureCategory.UNKNOWN

    def test_k_missing_optional_razorpay_fields(self):
        """Test K: Missing optional fields are handled safely without raising exceptions."""
        # Only description provided
        assert FailureClassifier.classify(
            error_description="Payment was declined by the bank due to insufficient funds."
        ) == FailureCategory.INSUFFICIENT_FUNDS

        # Only error_reason provided
        assert FailureClassifier.classify(
            error_reason="card_declined"
        ) == FailureCategory.CARD_DECLINED

        # None for all arguments
        assert FailureClassifier.classify(
            error_code=None,
            error_description=None,
            error_source=None,
            error_step=None,
            error_reason=None,
        ) == FailureCategory.UNKNOWN

        # classify_payment_entity with empty dict or None
        assert FailureClassifier.classify_payment_entity({}) == FailureCategory.UNKNOWN
        assert FailureClassifier.classify_payment_entity(None) == FailureCategory.UNKNOWN

    def test_payment_timeout_classification(self):
        """Additional taxonomy test: Payment session / user checkout timeout."""
        result = FailureClassifier.classify(
            error_code="BAD_REQUEST_ERROR",
            error_description="Payment window was closed before completion.",
            error_source="customer",
            error_reason="payment_timed_out",
        )
        assert result == FailureCategory.PAYMENT_TIMEOUT
