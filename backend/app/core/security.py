"""Razorpay webhook signature verification utility.

Implements HMAC-SHA256 signature verification against the raw request body,
following Razorpay's official webhook verification protocol.

Reference: https://razorpay.com/docs/webhooks/validate-test/
"""

import hashlib
import hmac
import logging

logger = logging.getLogger(__name__)


def verify_webhook_signature(
    raw_body: bytes,
    signature: str,
    webhook_secret: str,
) -> bool:
    """Verify a Razorpay webhook signature using HMAC-SHA256.

    The signature is computed over the exact raw request body bytes using
    the webhook secret as the HMAC key. This must be performed BEFORE any
    JSON parsing or transformation of the body.

    Args:
        raw_body: The exact raw bytes of the HTTP request body.
        signature: The value of the X-Razorpay-Signature header.
        webhook_secret: The webhook secret configured in the Razorpay dashboard.

    Returns:
        True if the signature is valid, False otherwise.
    """
    if not raw_body or not signature or not webhook_secret:
        logger.warning("Signature verification called with missing inputs")
        return False

    try:
        expected_signature = hmac.new(
            key=webhook_secret.encode("utf-8"),
            msg=raw_body,
            digestmod=hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)
    except Exception as exc:
        logger.error("Signature verification error: %s", exc.__class__.__name__)
        return False
