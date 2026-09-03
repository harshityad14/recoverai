"""Comprehensive test suite for the Razorpay webhook handler.

Tests cover:
A. Valid webhook signature → HTTP 200, event pushed to Redis
B. Invalid signature → rejected, nothing pushed to Redis
C. Malformed JSON → rejected safely
D. Missing signature → rejected safely
E. Unsupported event → handled safely without entering recovery workflow
F. Duplicate webhook → only one queue entry
G. payment.failed → correctly accepted
H. payment.captured → correctly accepted
"""

import hashlib
import hmac
import json
from typing import Any, Dict, Optional
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.core.queue import WEBHOOK_QUEUE_NAME, IDEMPOTENCY_KEY_PREFIX

# ─── Test Configuration ───

TEST_WEBHOOK_SECRET = "test_webhook_secret_for_phase2"


# ─── Fake Redis Client ───

class FakeRedis:
    """In-memory Redis substitute for unit testing.

    Implements the minimal RedisQueueClient protocol needed by the
    webhook handler and queue module without requiring a running Redis server.
    """

    def __init__(self):
        self._data: Dict[str, Any] = {}
        self._lists: Dict[str, list] = {}

    def lpush(self, name: str, *values: Any) -> int:
        if name not in self._lists:
            self._lists[name] = []
        for v in values:
            self._lists[name].insert(0, v)
        return len(self._lists[name])

    def rpop(self, name: str) -> Optional[str]:
        lst = self._lists.get(name, [])
        if lst:
            return lst.pop()
        return None

    def get(self, name: str) -> Optional[str]:
        return self._data.get(name)

    def set(self, name: str, value: Any, ex: Optional[int] = None) -> bool:
        self._data[name] = str(value)
        return True

    def llen(self, name: str) -> int:
        return len(self._lists.get(name, []))

    def lrange(self, name: str, start: int, end: int) -> list:
        lst = self._lists.get(name, [])
        if end == -1:
            end = len(lst)
        else:
            end = end + 1
        return lst[start:end]

    def ping(self) -> bool:
        return True


# ─── Helper Functions ───

def _build_payment_failed_payload(
    payment_id: str = "pay_TestPayment001",
    amount: int = 50000,
    currency: str = "INR",
) -> dict:
    """Build a realistic Razorpay payment.failed webhook payload."""
    return {
        "entity": "event",
        "event": "payment.failed",
        "account_id": "acc_TestAccount001",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount,
                    "currency": currency,
                    "status": "failed",
                    "method": "card",
                    "description": "Test order payment",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment was unsuccessful due to a temporary issue.",
                    "error_source": "customer",
                    "error_step": "payment_authentication",
                    "error_reason": "payment_failed",
                }
            }
        },
        "created_at": 1700000000,
    }


def _build_payment_captured_payload(
    payment_id: str = "pay_TestPayment002",
    amount: int = 75000,
    currency: str = "INR",
) -> dict:
    """Build a realistic Razorpay payment.captured webhook payload."""
    return {
        "entity": "event",
        "event": "payment.captured",
        "account_id": "acc_TestAccount001",
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "entity": "payment",
                    "amount": amount,
                    "currency": currency,
                    "status": "captured",
                    "method": "upi",
                    "description": "Test order payment - recovered",
                }
            }
        },
        "created_at": 1700000100,
    }


def _compute_signature(body: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature matching Razorpay's algorithm."""
    return hmac.new(
        key=secret.encode("utf-8"),
        msg=body,
        digestmod=hashlib.sha256,
    ).hexdigest()


def _post_webhook(
    client: TestClient,
    payload: dict | bytes | None = None,
    secret: str = TEST_WEBHOOK_SECRET,
    compute_sig: bool = True,
    signature_override: Optional[str] = None,
    event_id: Optional[str] = "evt_TestEvent001",
) -> Any:
    """Helper to POST a webhook with optional signature and event ID."""
    if payload is None:
        body = b""
    elif isinstance(payload, bytes):
        body = payload
    else:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")

    headers: Dict[str, str] = {"Content-Type": "application/json"}

    if signature_override is not None:
        headers["X-Razorpay-Signature"] = signature_override
    elif compute_sig and body:
        headers["X-Razorpay-Signature"] = _compute_signature(body, secret)

    if event_id:
        headers["X-Razorpay-Event-Id"] = event_id

    return client.post("/webhooks/razorpay", content=body, headers=headers)


# ─── Fixtures ───

@pytest.fixture()
def fake_redis():
    """Provide a fresh FakeRedis instance per test."""
    return FakeRedis()


@pytest.fixture()
def webhook_client(fake_redis):
    """Provide a TestClient with mocked Redis and webhook secret."""
    with patch("app.api.routes.webhook.get_redis", return_value=fake_redis), \
         patch("app.core.config.settings.RAZORPAY_WEBHOOK_SECRET", TEST_WEBHOOK_SECRET):
        with TestClient(app) as client:
            yield client


# ─── Test A: Valid webhook signature ───

class TestValidSignature:
    """A valid webhook with correct HMAC signature should be accepted and enqueued."""

    def test_returns_200(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        response = _post_webhook(webhook_client, payload)
        assert response.status_code == 200

    def test_response_status_ok(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        response = _post_webhook(webhook_client, payload)
        data = response.json()
        assert data["status"] == "ok"

    def test_event_pushed_to_redis(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        _post_webhook(webhook_client, payload)
        queue_length = fake_redis.llen(WEBHOOK_QUEUE_NAME)
        assert queue_length == 1

    def test_event_id_echoed(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        response = _post_webhook(webhook_client, payload, event_id="evt_Echo123")
        data = response.json()
        assert data["event_id"] == "evt_Echo123"


# ─── Test B: Invalid signature ───

class TestInvalidSignature:
    """A webhook with an incorrect signature must be rejected."""

    def test_returns_401(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        response = _post_webhook(
            webhook_client, payload,
            compute_sig=False,
            signature_override="invalid_hex_signature",
        )
        assert response.status_code == 401

    def test_nothing_pushed_to_redis(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        _post_webhook(
            webhook_client, payload,
            compute_sig=False,
            signature_override="invalid_hex_signature",
        )
        queue_length = fake_redis.llen(WEBHOOK_QUEUE_NAME)
        assert queue_length == 0

    def test_wrong_secret_rejected(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        response = _post_webhook(
            webhook_client, payload,
            secret="wrong_secret_value",
        )
        assert response.status_code == 401


# ─── Test C: Malformed JSON ───

class TestMalformedJson:
    """Malformed JSON bodies must be rejected safely."""

    def test_returns_400(self, webhook_client, fake_redis):
        bad_body = b"this is not json {{{["
        sig = _compute_signature(bad_body, TEST_WEBHOOK_SECRET)
        response = webhook_client.post(
            "/webhooks/razorpay",
            content=bad_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": "evt_Malformed001",
            },
        )
        assert response.status_code == 400

    def test_nothing_pushed_to_redis(self, webhook_client, fake_redis):
        bad_body = b"not-json"
        sig = _compute_signature(bad_body, TEST_WEBHOOK_SECRET)
        webhook_client.post(
            "/webhooks/razorpay",
            content=bad_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
                "X-Razorpay-Event-Id": "evt_Malformed002",
            },
        )
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 0


# ─── Test D: Missing signature ───

class TestMissingSignature:
    """Requests without X-Razorpay-Signature must be rejected."""

    def test_returns_400(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        body = json.dumps(payload).encode("utf-8")
        response = webhook_client.post(
            "/webhooks/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Event-Id": "evt_NoSig001",
            },
        )
        assert response.status_code == 400

    def test_nothing_pushed_to_redis(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        body = json.dumps(payload).encode("utf-8")
        webhook_client.post(
            "/webhooks/razorpay",
            content=body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Event-Id": "evt_NoSig002",
            },
        )
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 0


# ─── Test E: Unsupported event ───

class TestUnsupportedEvent:
    """Unsupported events should be acknowledged but NOT enqueued."""

    def test_returns_200(self, webhook_client, fake_redis):
        payload = {
            "entity": "event",
            "event": "refund.created",
            "account_id": "acc_TestAccount001",
            "contains": ["refund"],
            "payload": {"refund": {"entity": {"id": "rfnd_Test001"}}},
            "created_at": 1700000200,
        }
        response = _post_webhook(webhook_client, payload, event_id="evt_Unsupported001")
        assert response.status_code == 200

    def test_not_enqueued(self, webhook_client, fake_redis):
        payload = {
            "entity": "event",
            "event": "order.paid",
            "account_id": "acc_TestAccount001",
            "contains": ["order"],
            "payload": {"order": {"entity": {"id": "order_Test001"}}},
            "created_at": 1700000300,
        }
        _post_webhook(webhook_client, payload, event_id="evt_Unsupported002")
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 0


# ─── Test F: Duplicate webhook ───

class TestDuplicateWebhook:
    """Duplicate events (same X-Razorpay-Event-Id) must produce only one queue entry."""

    def test_only_one_queue_entry(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload()
        event_id = "evt_Duplicate001"

        # First delivery
        resp1 = _post_webhook(webhook_client, payload, event_id=event_id)
        assert resp1.status_code == 200

        # Second delivery (duplicate)
        resp2 = _post_webhook(webhook_client, payload, event_id=event_id)
        assert resp2.status_code == 200

        # Only one entry in the queue
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 1

    def test_duplicate_returns_ok(self, webhook_client, fake_redis):
        payload = _build_payment_captured_payload()
        event_id = "evt_Duplicate002"

        _post_webhook(webhook_client, payload, event_id=event_id)
        resp = _post_webhook(webhook_client, payload, event_id=event_id)

        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ─── Test G: payment.failed ───

class TestPaymentFailed:
    """payment.failed events must be correctly accepted and enqueued."""

    def test_accepted_and_enqueued(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload(payment_id="pay_Failed001")
        response = _post_webhook(webhook_client, payload, event_id="evt_Failed001")

        assert response.status_code == 200
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 1

        # Verify enqueued data contains the correct event type
        queued_raw = fake_redis.lrange(WEBHOOK_QUEUE_NAME, 0, 0)[0]
        queued_data = json.loads(queued_raw)
        assert queued_data["event_type"] == "payment.failed"

    def test_payload_preserved(self, webhook_client, fake_redis):
        payload = _build_payment_failed_payload(
            payment_id="pay_Failed002",
            amount=99900,
            currency="INR",
        )
        _post_webhook(webhook_client, payload, event_id="evt_Failed002")

        queued_raw = fake_redis.lrange(WEBHOOK_QUEUE_NAME, 0, 0)[0]
        queued_data = json.loads(queued_raw)
        inner_payment = queued_data["payload"]["payload"]["payment"]["entity"]
        assert inner_payment["id"] == "pay_Failed002"
        assert inner_payment["amount"] == 99900


# ─── Test H: payment.captured ───

class TestPaymentCaptured:
    """payment.captured events must be correctly accepted and enqueued."""

    def test_accepted_and_enqueued(self, webhook_client, fake_redis):
        payload = _build_payment_captured_payload(payment_id="pay_Captured001")
        response = _post_webhook(webhook_client, payload, event_id="evt_Captured001")

        assert response.status_code == 200
        assert fake_redis.llen(WEBHOOK_QUEUE_NAME) == 1

        queued_raw = fake_redis.lrange(WEBHOOK_QUEUE_NAME, 0, 0)[0]
        queued_data = json.loads(queued_raw)
        assert queued_data["event_type"] == "payment.captured"

    def test_payload_preserved(self, webhook_client, fake_redis):
        payload = _build_payment_captured_payload(
            payment_id="pay_Captured002",
            amount=150000,
        )
        _post_webhook(webhook_client, payload, event_id="evt_Captured002")

        queued_raw = fake_redis.lrange(WEBHOOK_QUEUE_NAME, 0, 0)[0]
        queued_data = json.loads(queued_raw)
        inner_payment = queued_data["payload"]["payload"]["payment"]["entity"]
        assert inner_payment["id"] == "pay_Captured002"
        assert inner_payment["amount"] == 150000
        assert inner_payment["status"] == "captured"
