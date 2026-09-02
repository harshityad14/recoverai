"""Pydantic schemas for Razorpay webhook payloads.

These schemas validate the basic structure of incoming Razorpay webhook events
after signature verification has passed. They do NOT model every field
exhaustively—only the fields required for routing and queue operations.

Reference: https://razorpay.com/docs/webhooks/payments/
"""

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# Supported event types in Phase 2
SUPPORTED_EVENT_TYPES = {
    "payment.failed",
    "payment.captured",
}


class WebhookPayload(BaseModel):
    """Validated Razorpay webhook event payload.

    Matches the official Razorpay webhook JSON structure:
    - entity: always "event"
    - event: the event type string (e.g., "payment.failed")
    - account_id: the merchant account identifier
    - contains: list of entity types present in payload (e.g., ["payment"])
    - payload: nested object containing the entity snapshots
    - created_at: Unix timestamp of the event
    """

    entity: str = Field(..., description="Always 'event' for webhook payloads")
    event: str = Field(..., description="Event type, e.g. 'payment.failed'")
    account_id: str = Field(..., description="Razorpay merchant account ID")
    contains: List[str] = Field(..., description="Entity types in the payload")
    payload: Dict[str, Any] = Field(..., description="Nested entity data")
    created_at: int = Field(..., description="Unix timestamp of event creation")


class WebhookResponse(BaseModel):
    """Response returned to Razorpay after successful webhook processing."""

    status: str = Field(default="ok", description="Acknowledgment status")
    event_id: Optional[str] = Field(default=None, description="Razorpay event ID echoed back")
