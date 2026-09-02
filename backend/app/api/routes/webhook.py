"""Razorpay webhook route handler.

Implements POST /webhooks/razorpay with:
- Raw body capture before JSON parsing
- HMAC-SHA256 signature verification via X-Razorpay-Signature
- Idempotency check via X-Razorpay-Event-Id
- Event validation and routing
- Redis queue enqueue for verified events
- Fast HTTP 200 acknowledgment

Reference: https://razorpay.com/docs/webhooks/
"""

import json
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Request

from app.core.config import settings
from app.core.queue import (
    enqueue_webhook_event,
    is_duplicate_event,
    mark_event_processed,
)
from app.core.redis import get_redis
from app.core.security import verify_webhook_signature
from app.schemas.webhook import (
    SUPPORTED_EVENT_TYPES,
    WebhookPayload,
    WebhookResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post(
    "/razorpay",
    response_model=WebhookResponse,
    summary="Razorpay Webhook Receiver",
    description=(
        "Receives Razorpay webhook events. Verifies the HMAC-SHA256 signature "
        "against the raw request body, checks for duplicate delivery via "
        "X-Razorpay-Event-Id, validates the event structure, and enqueues "
        "verified events onto Redis for downstream processing."
    ),
    responses={
        200: {"description": "Webhook received and enqueued successfully"},
        400: {"description": "Malformed request body or missing signature"},
        401: {"description": "Invalid webhook signature"},
    },
)
async def receive_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None),
    x_razorpay_event_id: Optional[str] = Header(None),
) -> WebhookResponse:
    """Handle incoming Razorpay webhook events.

    Processing pipeline:
    1. Read raw request body (bytes)
    2. Validate X-Razorpay-Signature header is present
    3. Verify HMAC-SHA256 signature against raw body
    4. Check idempotency via X-Razorpay-Event-Id
    5. Parse and validate JSON payload structure
    6. Check event type is supported
    7. Enqueue verified event to Redis
    8. Return HTTP 200 immediately
    """
    # ── Step 1: Read raw body BEFORE any parsing ──
    raw_body = await request.body()

    if not raw_body:
        logger.warning("Received empty webhook request body")
        raise HTTPException(status_code=400, detail="Empty request body")

    # ── Step 2: Require signature header ──
    if not x_razorpay_signature:
        logger.warning("Webhook request missing X-Razorpay-Signature header")
        raise HTTPException(
            status_code=400,
            detail="Missing X-Razorpay-Signature header",
        )

    # ── Step 3: Verify HMAC-SHA256 signature ──
    webhook_secret = settings.RAZORPAY_WEBHOOK_SECRET
    if not webhook_secret:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not configured")
        raise HTTPException(status_code=500, detail="Webhook secret not configured")

    is_valid = verify_webhook_signature(raw_body, x_razorpay_signature, webhook_secret)
    if not is_valid:
        logger.warning("Invalid webhook signature rejected")
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    # ── Step 4: Idempotency check via X-Razorpay-Event-Id ──
    redis_client = get_redis()
    if redis_client and x_razorpay_event_id:
        if is_duplicate_event(redis_client, x_razorpay_event_id):
            logger.info(
                "Duplicate webhook event ignored: event_id=%s",
                x_razorpay_event_id,
            )
            return WebhookResponse(status="ok", event_id=x_razorpay_event_id)

    # ── Step 5: Parse and validate JSON payload ──
    try:
        payload_dict = json.loads(raw_body)
    except (json.JSONDecodeError, ValueError) as exc:
        logger.warning("Malformed JSON in webhook body: %s", exc)
        raise HTTPException(status_code=400, detail="Malformed JSON body")

    try:
        webhook_event = WebhookPayload(**payload_dict)
    except Exception as exc:
        logger.warning("Webhook payload validation failed: %s", exc)
        raise HTTPException(
            status_code=400,
            detail="Invalid webhook payload structure",
        )

    # ── Step 6: Check event type ──
    event_type = webhook_event.event
    if event_type not in SUPPORTED_EVENT_TYPES:
        logger.info(
            "Unsupported webhook event type received: %s (acknowledged without processing)",
            event_type,
        )
        # Acknowledge receipt but do not enqueue for recovery processing
        return WebhookResponse(status="ok", event_id=x_razorpay_event_id)

    # ── Step 7: Enqueue to Redis ──
    event_data = {
        "event_id": x_razorpay_event_id,
        "event_type": event_type,
        "account_id": webhook_event.account_id,
        "payload": payload_dict,
    }

    if redis_client:
        enqueue_webhook_event(redis_client, event_data)

        # Mark event as processed for idempotency
        if x_razorpay_event_id:
            mark_event_processed(redis_client, x_razorpay_event_id)
    else:
        logger.warning(
            "Redis unavailable — event acknowledged but NOT enqueued: event_id=%s",
            x_razorpay_event_id,
        )

    # ── Step 8: Fast acknowledgment ──
    logger.info(
        "Webhook processed: event_type=%s, event_id=%s",
        event_type,
        x_razorpay_event_id,
    )
    return WebhookResponse(status="ok", event_id=x_razorpay_event_id)
