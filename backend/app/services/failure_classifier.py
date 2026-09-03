"""Deterministic Failure Classification Service.

Classifies payment failures into domain taxonomy categories based on official
Razorpay failure fields (error_code, error_description, error_source, error_step, error_reason).
Does NOT use LLMs. Does NOT invent Razorpay error codes.
"""

import logging
from typing import Any, Dict, Optional

from app.schemas.taxonomy import FailureCategory

logger = logging.getLogger(__name__)

# Keywords associated with risk and fraud signals
RISK_KEYWORDS = (
    "fraud",
    "blacklisted",
    "suspicious",
    "high_risk",
    "high risk",
    "risk threshold",
    "security violation",
    "blocked due to risk",
    "risk check",
    "restricted card",
)

# Reasons associated with risk
RISK_REASONS = {
    "payment_risk",
    "risk_threshold_exceeded",
    "fraud",
    "high_risk",
    "blacklisted",
    "suspicious",
    "card_blacklisted",
    "customer_blacklisted",
    "ip_blacklisted",
    "restricted_card",
}

# Reasons associated with insufficient funds
INSUFFICIENT_FUNDS_REASONS = {
    "insufficient_funds",
    "insufficient_balance",
    "low_balance",
}

INSUFFICIENT_FUNDS_KEYWORDS = (
    "insufficient funds",
    "insufficient balance",
    "low balance",
    "not enough funds",
    "balance insufficient",
)

# Reasons associated with card decline
CARD_DECLINED_REASONS = {
    "card_declined",
    "card_inactive",
    "card_blocked",
    "card_expired",
    "invalid_card",
    "do_not_honor",
    "pickup_card",
    "declined_by_bank",
    "international_card_not_supported",
    "card_not_supported",
    "card_limit_exceeded",
    "transaction_not_permitted",
}

CARD_DECLINED_KEYWORDS = (
    "card was declined",
    "card is inactive",
    "card has expired",
    "card expired",
    "card is blocked",
    "declined by issuing bank",
    "declined by bank",
    "transaction not permitted",
    "do not honor",
    "invalid card details",
)

# Reasons associated with 3DS / OTP verification
THREE_DS_REASONS = {
    "3ds_failed",
    "three_ds_failed",
    "invalid_otp",
    "otp_not_entered",
    "otp_expired",
    "3ds_timeout",
    "authentication_timeout",
}

THREE_DS_KEYWORDS = (
    "3ds",
    "3d secure",
    "3-d secure",
    "otp incorrect",
    "invalid otp",
    "otp expired",
    "otp was not entered",
    "incorrect otp",
    "authentication failed at 3d secure",
)

# Reasons associated with credentials and PIN auth
AUTH_REASONS = {
    "authentication_failed",
    "invalid_credentials",
    "pin_incorrect",
    "mpin_incorrect",
    "password_incorrect",
    "incorrect_pin",
    "invalid_pin",
}

AUTH_KEYWORDS = (
    "pin is incorrect",
    "incorrect pin",
    "invalid pin",
    "mpin incorrect",
    "authentication failed",
    "credentials invalid",
    "invalid credentials",
)

# Reasons associated with bank / gateway timeouts
BANK_TIMEOUT_REASONS = {
    "bank_timed_out",
    "bank_timeout",
    "gateway_timed_out",
    "gateway_timeout",
    "issuer_timeout",
}

BANK_TIMEOUT_KEYWORDS = (
    "bank timed out",
    "bank did not respond",
    "bank server timeout",
    "bank timeout",
    "gateway timed out",
    "gateway timeout",
    "issuer timed out",
)

# Reasons associated with checkout / user session timeout
PAYMENT_TIMEOUT_REASONS = {
    "payment_timed_out",
    "user_timed_out",
    "session_timed_out",
    "payment_cancelled_by_user",
    "window_closed",
}

PAYMENT_TIMEOUT_KEYWORDS = (
    "payment timed out",
    "payment window closed",
    "session expired",
    "user took too long",
    "checkout session timed out",
)

# Keywords associated with network and gateway communication errors
NETWORK_KEYWORDS = (
    "network error",
    "connection error",
    "network failure",
    "connection reset",
    "connection timed out",
    "communication error",
    "temporary network issue",
    "unable to reach bank network",
    "temporary technical issue",
)


class FailureClassifier:
    """Deterministic payment failure classifier.

    Maps Razorpay webhook failure fields into the 9 allowed domain taxonomy categories:
    - BANK_TIMEOUT
    - INSUFFICIENT_FUNDS
    - CARD_DECLINED
    - NETWORK_ERROR
    - AUTHENTICATION_FAILURE
    - THREE_DS_FAILURE
    - PAYMENT_TIMEOUT
    - FRAUD_RISK
    - UNKNOWN
    """

    @staticmethod
    def classify(
        error_code: Optional[str] = None,
        error_description: Optional[str] = None,
        error_source: Optional[str] = None,
        error_step: Optional[str] = None,
        error_reason: Optional[str] = None,
    ) -> FailureCategory:
        """Classify a failure into a deterministic domain taxonomy category.

        Evaluation order prioritizes security (FRAUD_RISK), followed by concrete
        user/balance issues (INSUFFICIENT_FUNDS, 3DS, AUTH, CARD_DECLINED),
        transient issues (BANK_TIMEOUT, PAYMENT_TIMEOUT, NETWORK_ERROR), and UNKNOWN.

        Args:
            error_code: Razorpay error code (e.g. BAD_REQUEST_ERROR, GATEWAY_ERROR).
            error_description: Human-readable error description from Razorpay.
            error_source: Origin of error (customer, business, bank, gateway, razorpay).
            error_step: Transaction step (payment_initiation, payment_authentication, etc.).
            error_reason: Specific error reason identifier.

        Returns:
            FailureCategory: Deterministic taxonomy category.
        """
        code = (error_code or "").strip().lower()
        desc = (error_description or "").strip().lower()
        source = (error_source or "").strip().lower()
        step = (error_step or "").strip().lower()
        reason = (error_reason or "").strip().lower()

        # If completely empty or missing failure information
        if not any([code, desc, source, step, reason]):
            return FailureCategory.UNKNOWN

        # ── 1. FRAUD_RISK (Highest priority for security) ──
        if step == "payment_risk":
            return FailureCategory.FRAUD_RISK
        if reason in RISK_REASONS or any(kw in reason for kw in ("fraud", "risk", "blacklisted")):
            return FailureCategory.FRAUD_RISK
        if any(kw in desc for kw in RISK_KEYWORDS):
            return FailureCategory.FRAUD_RISK

        # ── 2. INSUFFICIENT_FUNDS ──
        if reason in INSUFFICIENT_FUNDS_REASONS:
            return FailureCategory.INSUFFICIENT_FUNDS
        if any(kw in desc for kw in INSUFFICIENT_FUNDS_KEYWORDS):
            return FailureCategory.INSUFFICIENT_FUNDS

        # ── 3. THREE_DS_FAILURE ──
        if reason in THREE_DS_REASONS:
            return FailureCategory.THREE_DS_FAILURE
        if any(kw in desc for kw in THREE_DS_KEYWORDS):
            return FailureCategory.THREE_DS_FAILURE
        if step == "payment_authentication" and any(k in desc or k in reason for k in ("otp", "3ds", "three_ds")):
            return FailureCategory.THREE_DS_FAILURE

        # ── 4. AUTHENTICATION_FAILURE (PIN, MPIN, credentials, generic auth) ──
        if reason in AUTH_REASONS:
            return FailureCategory.AUTHENTICATION_FAILURE
        if any(kw in desc for kw in AUTH_KEYWORDS):
            return FailureCategory.AUTHENTICATION_FAILURE
        if step == "payment_authentication" and not any(kw in desc for kw in NETWORK_KEYWORDS):
            return FailureCategory.AUTHENTICATION_FAILURE

        # ── 5. CARD_DECLINED ──
        if reason in CARD_DECLINED_REASONS:
            return FailureCategory.CARD_DECLINED
        if any(kw in desc for kw in CARD_DECLINED_KEYWORDS):
            return FailureCategory.CARD_DECLINED
        if "card" in desc and "decline" in desc:
            return FailureCategory.CARD_DECLINED

        # ── 6. BANK_TIMEOUT ──
        if reason in BANK_TIMEOUT_REASONS:
            return FailureCategory.BANK_TIMEOUT
        if any(kw in desc for kw in BANK_TIMEOUT_KEYWORDS):
            return FailureCategory.BANK_TIMEOUT
        if source in ("bank", "gateway") and any(kw in desc for kw in ("timed out", "timeout", "did not respond")):
            return FailureCategory.BANK_TIMEOUT

        # ── 7. PAYMENT_TIMEOUT (Session / User abandonment) ──
        if reason in PAYMENT_TIMEOUT_REASONS:
            return FailureCategory.PAYMENT_TIMEOUT
        if any(kw in desc for kw in PAYMENT_TIMEOUT_KEYWORDS):
            return FailureCategory.PAYMENT_TIMEOUT

        # ── 8. NETWORK_ERROR (Gateway / Network transport error) ──
        if reason in ("network_error", "network_failure", "connection_failure", "connection_error"):
            return FailureCategory.NETWORK_ERROR
        if any(kw in desc for kw in NETWORK_KEYWORDS):
            return FailureCategory.NETWORK_ERROR
        if code == "gateway_error":
            return FailureCategory.NETWORK_ERROR

        # ── 9. UNKNOWN (Conservative fallback) ──
        logger.info(
            "Failure details could not be mapped to specific taxonomy: code=%s, reason=%s",
            error_code,
            error_reason,
        )
        return FailureCategory.UNKNOWN

    @classmethod
    def classify_payment_entity(cls, payment_entity: Dict[str, Any]) -> FailureCategory:
        """Helper to classify directly from a Razorpay payment entity dict.

        Args:
            payment_entity: The payment dictionary from payload.payment.entity.

        Returns:
            FailureCategory: Deterministic taxonomy category.
        """
        if not payment_entity or not isinstance(payment_entity, dict):
            return FailureCategory.UNKNOWN

        return cls.classify(
            error_code=payment_entity.get("error_code"),
            error_description=payment_entity.get("error_description"),
            error_source=payment_entity.get("error_source"),
            error_step=payment_entity.get("error_step"),
            error_reason=payment_entity.get("error_reason"),
        )
