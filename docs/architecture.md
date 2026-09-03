# RecoverAI &mdash; System Architecture & Technical Design

## 1. Overview
RecoverAI is an autonomous payment recovery agent designed for the Razorpay ecosystem. It intercepts payment failure webhooks, evaluates failure reasons against a domain taxonomy, pulls customer context, and triggers guarded recovery strategies.

---

## 2. End-to-End Pipeline Architecture

```text
Razorpay payment.failed webhook
        ↓
Webhook Handler
        ↓
Signature Verification
        ↓
Redis Queue
        ↓
Analysis Service
        ↓
Failure Taxonomy + Customer Context
        ↓
LLM Decision Engine
        ↓
Structured Decision
        ↓
Deterministic Safety Guard
        ↓
Action Executor
        ↓
Razorpay Test Mode
        ↓
payment.captured / payment.failed
        ↓
Outcome Tracker
        ↓
PostgreSQL
        ↓
Dashboard + Audit Log
```

---

## 3. Component Breakdown

### 1. Webhook Handler & Signature Verification
- **Purpose**: Authenticates Razorpay webhook payloads using HMAC-SHA256 signature verification (`X-Razorpay-Signature`).
- **Safety**: Unverified requests are immediately dropped with HTTP 400.
- **Phase**: Scheduled for Phase 2.

### 2. Redis Queue
- **Purpose**: Decouples webhook ingestion from LLM evaluation and recovery workflows to ensure low-latency webhook acknowledgments (< 200ms).
- **Phase**: Connection configured in Phase 1; worker queue integration in Phase 2.

### 3. Analysis Service (Failure Taxonomy & Context)
- **Purpose**: Maps Razorpay error codes (e.g., `BAD_REQUEST_PAYMENT_TIMED_OUT`, `GATEWAY_ERROR`, `INSUFFICIENT_FUNDS`) to an actionable domain taxonomy and enriches failure events with customer profile history.
- **Phase**: Scheduled for Phase 3.

### 4. LLM Decision Engine
- **Purpose**: Evaluates the enriched failure event and generates a structured recovery strategy (e.g., smart retry, alternative payment method link via WhatsApp/SMS, customer discount offer, delay window).
- **Phase**: Scheduled for Phase 3.

### 5. Deterministic Safety Guard
- **Purpose**: Hard business rule validation layer. Ensures LLM recommendations do not violate retry limits, frequency caps, or customer communication policies before any action is executed.
- **Phase**: Scheduled for Phase 3.

### 6. Action Executor & Razorpay Integration
- **Purpose**: Dispatches verified recovery actions against Razorpay Test Mode APIs (e.g., generating payment links, initiating customer re-prompts).
- **Phase**: Scheduled for Phase 4.

### 7. Outcome Tracker, PostgreSQL & Dashboard
- **Purpose**: Tracks recovery outcomes (`payment.captured` or final `payment.failed`), persists audit events to PostgreSQL, and surfaces real-time metrics on the React dashboard.
- **Phase**: PostgreSQL config and base schema in Phase 1; complete telemetry in Phase 4.

---

## 4. Transaction Lifecycle & Attribution Semantics

To prevent false attribution of payment recoveries, RecoverAI distinguishes between organic captures and AI-assisted recoveries:

- **`FAILED`**: Payment failed and has not yet been successfully recovered.
- **`RECOVERY_PENDING`**: RecoverAI has identified the payment for recovery processing.
- **`CAPTURED`**: Razorpay reports the payment was successfully captured, but without verified evidence that RecoverAI caused the success (e.g., customer completed checkout organically).
- **`RECOVERED`**: Payment was successfully captured as a direct result of a verified RecoverAI recovery action.
- **`STOPPED`**: RecoverAI has determined that recovery should not continue.
