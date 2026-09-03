"""Failure Taxonomy enumeration and constants.

Defines the allowed domain taxonomy categories for classifying Razorpay payment failures.
"""

from enum import Enum


class FailureCategory(str, Enum):
    """Normalized payment failure taxonomy categories."""

    BANK_TIMEOUT = "BANK_TIMEOUT"
    INSUFFICIENT_FUNDS = "INSUFFICIENT_FUNDS"
    CARD_DECLINED = "CARD_DECLINED"
    NETWORK_ERROR = "NETWORK_ERROR"
    AUTHENTICATION_FAILURE = "AUTHENTICATION_FAILURE"
    THREE_DS_FAILURE = "THREE_DS_FAILURE"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    FRAUD_RISK = "FRAUD_RISK"
    UNKNOWN = "UNKNOWN"
