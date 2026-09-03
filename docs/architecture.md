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

### 4. LLM Decision Engine (Phase 4 — Advisory Recommender)
- **Purpose**: Consumes the normalized `PaymentAnalysis` from Phase 3 and produces a `RecoveryDecision` recommending exactly one of `RETRY`, `PAYMENT_LINK`, `REMINDER`, or `STOP`.
- **Architecture**: `PaymentAnalysis → DecisionEngine → LLMClient (Protocol) → RecoveryDecision`
- **Provider**: Google Gemini via `GeminiLLMClient` adapter (production). `MockLLMClient` for tests. The `LLMClient` protocol allows future provider swaps without changing the `DecisionEngine`.
- **Boundary**: The Decision Engine is an advisory RECOMMENDER only. It cannot execute actions, call Razorpay APIs, or modify transaction state. Its output is a suggestion — not a permission or authorization.
- **Safe Fallback**: On any LLM provider error, timeout, malformed response, or validation failure, the engine deterministically returns `action=STOP, confidence=0.0`.
- **Phase**: Implemented in Phase 4.

### 5. Deterministic Safety Guard (Phase 5 — Authoritative Enforcer)
- **Purpose**: Hard business rule validation layer. Independently validates, overrides, or blocks LLM recommendations before any action is executed. Enforces retry limits, frequency caps, risk flag blocking, transaction state guards, and customer communication policies.
- **Boundary**: Phase 5 is the sole authorization gateway. It can ALLOW, BLOCK, or OVERRIDE any LLM recommendation regardless of confidence.
- **Phase**: Scheduled for Phase 5.

### 6. Action Executor & Razorpay Integration
- **Purpose**: Dispatches verified recovery actions against Razorpay Test Mode APIs (e.g., generating payment links, initiating customer re-prompts). Executes only if Phase 5 allows.
- **Phase**: Scheduled for Phase 6.

### 7. Outcome Tracker, PostgreSQL & Dashboard
- **Purpose**: Tracks recovery outcomes (`payment.captured` or final `payment.failed`), persists audit events to PostgreSQL, and surfaces real-time metrics on the React dashboard.
- **Phase**: PostgreSQL config and base schema in Phase 1; complete telemetry in Phase 7.

---

## 4. Transaction Lifecycle & Attribution Semantics

To prevent false attribution of payment recoveries, RecoverAI distinguishes between organic captures and AI-assisted recoveries:

- **`FAILED`**: Payment failed and has not yet been successfully recovered.
- **`RECOVERY_PENDING`**: RecoverAI has identified the payment for recovery processing.
- **`CAPTURED`**: Razorpay reports the payment was successfully captured, but without verified evidence that RecoverAI caused the success (e.g., customer completed checkout organically).
- **`RECOVERED`**: Payment was successfully captured as a direct result of a verified RecoverAI recovery action.
- **`STOPPED`**: RecoverAI has determined that recovery should not continue.

---

## 5. Decision Engine Pipeline & Responsibility Boundary

**"LLM recommends. Deterministic safety guard decides."**

```text
Phase 3 Normalized PaymentAnalysis
               │
               ▼
   ┌─────────────────────────────────────────────┐
   │  Phase 4: DecisionEngine.recommend_action() │
   │  (ADVISORY — produces RECOMMENDATION only)  │
   └──────────────────┬──────────────────────────┘
                      │
                      ▼
            RecoveryDecision
            (action, confidence, rationale)
            ⚠️ RECOMMENDATION, not permission
                      │
                      ▼
   ┌──────────────────────────────────────────────┐
   │  Phase 5: Deterministic Safety Guard         │
   │  (AUTHORITATIVE — makes FINAL decision)      │
   │  Can ALLOW, BLOCK, or OVERRIDE               │
   └──────────────────┬───────────────────────────┘
                      │
                      ▼
   ┌──────────────────────────────────────────────┐
   │  Phase 6: Action Executor                    │
   │  (Executes ONLY if Phase 5 allows)           │
   └──────────────────────────────────────────────┘
```

The LLM has zero execution privileges. It cannot call Razorpay APIs, modify transaction states, create payment links, retry payments, send customer messages, or bypass safety rules.
