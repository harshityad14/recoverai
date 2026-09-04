"""Razorpay REST Client Abstraction for Test Mode.

Provides strongly-typed, secure interaction with the official Razorpay REST API
for generating Payment Links in Test Mode.

CRITICAL SECURITY RULES:
- Test Mode ONLY: Live Mode (`rzp_live_...`) is strictly prohibited and rejected.
- Credentials loaded from environment configuration; never hard-coded.
- Credentials, secrets, and raw authentication headers are NEVER logged or exposed.
- All network operations use configurable timeouts and structured error handling.
"""

import logging
from typing import Any, Dict, Optional
import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Exception Hierarchy
# ---------------------------------------------------------------------------


class RazorpayClientError(Exception):
    """Base exception for all Razorpay client errors."""

    def __init__(self, message: str, error_code: Optional[str] = None):
        super().__init__(message)
        self.message = message
        self.error_code = error_code or "RAZORPAY_CLIENT_ERROR"


class RazorpaySecurityError(RazorpayClientError):
    """Raised when Live Mode keys or prohibited security configurations are detected."""

    def __init__(self, message: str = "Live Mode is strictly prohibited. RecoverAI only operates in Test Mode."):
        super().__init__(message, error_code="LIVE_MODE_PROHIBITED")


class RazorpayAuthenticationError(RazorpayClientError):
    """Raised when Razorpay credentials fail authentication (HTTP 401)."""

    def __init__(self, message: str = "Razorpay authentication failed; check Key ID and Secret."):
        super().__init__(message, error_code="AUTHENTICATION_FAILURE")


class RazorpayTimeoutError(RazorpayClientError):
    """Raised when an API call to Razorpay times out."""

    def __init__(self, message: str = "Razorpay API request timed out."):
        super().__init__(message, error_code="GATEWAY_TIMEOUT")


class RazorpayNetworkError(RazorpayClientError):
    """Raised when connection or network failure prevents reaching Razorpay."""

    def __init__(self, message: str = "Network error connecting to Razorpay API."):
        super().__init__(message, error_code="NETWORK_FAILURE")


class RazorpayResponseError(RazorpayClientError):
    """Raised when Razorpay returns an unexpected or unparseable response."""

    def __init__(self, message: str = "Malformed or unparseable response received from Razorpay."):
        super().__init__(message, error_code="INVALID_RESPONSE")


class RazorpayAPIError(RazorpayClientError):
    """Raised when Razorpay returns an API error response (HTTP 4xx/5xx)."""

    def __init__(
        self,
        message: str,
        status_code: int,
        error_code: Optional[str] = None,
        error_description: Optional[str] = None,
    ):
        super().__init__(message, error_code=error_code or "API_ERROR")
        self.status_code = status_code
        self.error_description = error_description


# ---------------------------------------------------------------------------
# Razorpay Client
# ---------------------------------------------------------------------------


class RazorpayClient:
    """Official Razorpay REST API Client for Test Mode recovery actions."""

    def __init__(
        self,
        key_id: Optional[str] = None,
        key_secret: Optional[str] = None,
        base_url: str = "https://api.razorpay.com",
        timeout: float = 10.0,
    ):
        """Initialize RazorpayClient with Test Mode validation.

        Args:
            key_id: Razorpay API Key ID (must be a test key, starting with rzp_test_).
            key_secret: Razorpay API Key Secret.
            base_url: Base URL for Razorpay API (default: https://api.razorpay.com).
            timeout: Request timeout in seconds (default: 10.0s).

        Raises:
            RazorpaySecurityError: If a Live Mode key (rzp_live_) is provided.
        """
        self.key_id = key_id or settings.RAZORPAY_KEY_ID or ""
        self.key_secret = key_secret or settings.RAZORPAY_KEY_SECRET or ""
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

        self._validate_mode()

    def _validate_mode(self) -> None:
        """Enforce strict Test Mode policy. Never allow Live Mode keys."""
        if self.key_id.startswith("rzp_live_"):
            logger.critical("ATTEMPTED TO USE RAZORPAY LIVE KEY. Live mode is strictly prohibited.")
            raise RazorpaySecurityError("Live Mode is strictly prohibited. RecoverAI only operates in Test Mode.")

    @property
    def is_test_mode(self) -> bool:
        """Return True if the client is configured with a Test Mode key."""
        return self.key_id.startswith("rzp_test_") or "test" in self.key_id.lower()

    def create_payment_link(
        self,
        amount: int,
        currency: str = "INR",
        reference_id: Optional[str] = None,
        description: Optional[str] = None,
        customer: Optional[Dict[str, Any]] = None,
        notify: Optional[Dict[str, bool]] = None,
        reminder_enable: bool = True,
        notes: Optional[Dict[str, Any]] = None,
        callback_url: Optional[str] = None,
        callback_method: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a standard Razorpay Payment Link via POST /v1/payment_links.

        Args:
            amount: Transaction amount in smallest currency unit (e.g., paise for INR).
            currency: Three-letter ISO currency code (default: INR).
            reference_id: Unique merchant reference ID for idempotency and tracking.
            description: Customer-facing description for the recovery link.
            customer: Optional customer details (name, contact, email).
            notify: Notification channels dictionary (e.g. {"sms": True, "email": True}).
            reminder_enable: Whether automated reminders are enabled for this link.
            notes: Key-value metadata attached to the payment link.
            callback_url: Optional merchant redirect URL upon payment.
            callback_method: Method for callback (e.g. "get").

        Returns:
            Dict[str, Any]: Parsed response dictionary from Razorpay.

        Raises:
            RazorpaySecurityError: If live mode is configured.
            RazorpayAuthenticationError: If HTTP 401 Unauthorized is returned.
            RazorpayTimeoutError: If the request times out.
            RazorpayNetworkError: If a connection error occurs.
            RazorpayResponseError: If the response is malformed or not JSON.
            RazorpayAPIError: If Razorpay returns an API error status (4xx/5xx).
        """
        self._validate_mode()

        if amount <= 0:
            raise RazorpayAPIError(
                message=f"Invalid payment link amount {amount}; must be positive.",
                status_code=400,
                error_code="BAD_REQUEST_ERROR",
            )

        endpoint = f"{self.base_url}/v1/payment_links"

        payload: Dict[str, Any] = {
            "amount": int(amount),
            "currency": str(currency).upper(),
            "accept_partial": False,
            "reference_id": reference_id,
            "description": description or "RecoverAI Payment Recovery Link",
            "reminder_enable": reminder_enable,
            "notify": notify if notify is not None else {"sms": True, "email": True},
        }

        if customer:
            payload["customer"] = customer

        if notes:
            payload["notes"] = notes

        if callback_url:
            payload["callback_url"] = callback_url
            if callback_method:
                payload["callback_method"] = callback_method

        logger.info(
            "Creating Razorpay Payment Link: amount=%d %s, reference_id=%s",
            payload["amount"],
            payload["currency"],
            reference_id,
        )

        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(
                    endpoint,
                    json=payload,
                    auth=(self.key_id, self.key_secret),
                    headers={"Content-Type": "application/json"},
                )
        except httpx.TimeoutException as exc:
            logger.error("Timeout connecting to Razorpay for reference_id=%s: %s", reference_id, exc)
            raise RazorpayTimeoutError(f"Razorpay request timed out after {self.timeout}s") from exc
        except (httpx.ConnectError, httpx.NetworkError) as exc:
            logger.error("Network error connecting to Razorpay for reference_id=%s: %s", reference_id, exc)
            raise RazorpayNetworkError(f"Network error communicating with Razorpay: {exc}") from exc
        except Exception as exc:
            logger.error("Unexpected error connecting to Razorpay: %s", exc)
            raise RazorpayNetworkError(f"Unexpected connection error: {exc}") from exc

        # ── Handle HTTP Status Codes ──
        if response.status_code == 401:
            logger.error("Razorpay authentication failed (HTTP 401)")
            raise RazorpayAuthenticationError("Razorpay credentials invalid or unauthorized")

        try:
            data = response.json()
        except Exception as exc:
            logger.error("Malformed non-JSON response from Razorpay (HTTP %d): %s", response.status_code, exc)
            raise RazorpayResponseError(f"Invalid JSON response from Razorpay (status {response.status_code})") from exc

        if not isinstance(data, dict):
            logger.error("Unexpected JSON structure from Razorpay: %s", type(data))
            raise RazorpayResponseError("Razorpay response is not a JSON object")

        if response.is_error:
            error_data = data.get("error", {})
            err_code = error_data.get("code") if isinstance(error_data, dict) else None
            err_desc = (
                error_data.get("description")
                if isinstance(error_data, dict)
                else str(data.get("error"))
            )
            logger.warning(
                "Razorpay returned error (HTTP %d): code=%s, desc=%s",
                response.status_code,
                err_code,
                err_desc,
            )
            raise RazorpayAPIError(
                message=f"Razorpay API error ({response.status_code}): {err_desc or err_code}",
                status_code=response.status_code,
                error_code=err_code,
                error_description=err_desc,
            )

        logger.info(
            "Successfully created Razorpay Payment Link: id=%s, short_url=%s",
            data.get("id"),
            data.get("short_url"),
        )
        return data
