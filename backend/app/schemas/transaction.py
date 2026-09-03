"""Transaction schemas and lifecycle statuses."""

from enum import Enum


class TransactionStatus(str, Enum):
    """Transaction lifecycle progression statuses.

    FAILED: Payment failed and has not yet been successfully recovered.
    RECOVERY_PENDING: RecoverAI has identified the payment for recovery processing.
    CAPTURED: Razorpay reports the payment was successfully captured, but there is
              not yet evidence that RecoverAI caused the success.
    RECOVERED: Payment was successfully captured as a result of a RecoverAI recovery action.
    STOPPED: RecoverAI has determined that recovery should not continue.
    """

    FAILED = "FAILED"
    RECOVERY_PENDING = "RECOVERY_PENDING"
    CAPTURED = "CAPTURED"
    RECOVERED = "RECOVERED"
    STOPPED = "STOPPED"
