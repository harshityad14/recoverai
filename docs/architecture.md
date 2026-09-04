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
- **Core Principle**: "LLM recommendations are untrusted input. The deterministic Safety Guard is the final authority."
- **Rules Priority**:
  1. Already CAPTURED/RECOVERED
  2. Already STOPPED
  3. Invalid decision
  4. STOP recommendation
  5. Confidence threshold
  6. Retry attempt limit
  7. Action eligibility
  8. APPROVE
- **Isolation**: Pure deterministic business logic with zero external API calls (no Gemini, no Razorpay, no Redis, no network).
- **Phase**: Implemented in Phase 5.

### 6. Action Executor & Razorpay Test Mode Integration (Phase 6)
- **Purpose**: Dispatches verified recovery actions against Razorpay Test Mode APIs (`POST /v1/payment_links`). Executes only when authorized by Phase 5 Safety Guard.
- **Core Principle**: "Only the final action produced by the deterministic Safety Guard may reach the Action Executor."
- **Recovery Lifecycle Boundary**: "Payment Link creation is not equivalent to payment recovery. RecoverAI marks a transaction RECOVERED only after the corresponding successful payment event is verified."
- **Security**: Strictly enforces Test Mode (`rzp_test_...`). Rejects Live Mode (`rzp_live_...`). Never logs or leaks API secrets.
- **Idempotency**: Prevents duplicate link generation by checking active recovery records before dispatching external API requests.
- **Phase**: Implemented in Phase 6.

### 7. Outcome Tracker, PostgreSQL & Dashboard
- **Purpose**: Tracks recovery outcomes (`payment.captured` or final `payment.failed`), persists audit events to PostgreSQL, and surfaces real-time metrics on the React dashboard.
- **Phase**: PostgreSQL config and base schema in Phase 1; complete telemetry in Phase 7.

---

## 4. Transaction Lifecycle & Attribution Semantics

To prevent false attribution of payment recoveries, RecoverAI distinguishes between organic captures and AI-assisted recoveries:

- **`FAILED`**: Payment failed and has not yet been successfully recovered.
- **`RECOVERY_PENDING`**: RecoverAI has identified the payment for recovery processing and dispatched a recovery action (e.g., created a payment link).
- **`CAPTURED`**: Razorpay reports the payment was successfully captured organically, without verified evidence that RecoverAI caused the success.
- **`RECOVERED`**: Payment was successfully captured as a direct result of a verified RecoverAI recovery action.
- **`STOPPED`**: RecoverAI has determined that recovery should not continue.

---

## 5. Decision Engine Pipeline & Responsibility Boundary

**"LLM recommends. Deterministic safety guard decides."**

> "LLM recommendations are untrusted input. The deterministic Safety Guard is the final authority."

> "Only the final action produced by the deterministic Safety Guard may reach the Action Executor."

> "Payment Link creation is not equivalent to payment recovery. RecoverAI marks a transaction RECOVERED only after the corresponding successful payment event is verified."

```text
Safety Guard
     ↓
SafetyDecision
     ↓
Action Executor
     ↓
Razorpay Client
     ↓
Razorpay Test Mode
     ↓
payment.captured / payment.failed
     ↓
Outcome Tracker
```

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
            SafetyDecision
            (final_action, decision, rule_id)
            🔒 AUTHORITATIVE FINAL ACTION
                      │
                      ▼
   ┌──────────────────────────────────────────────┐
   │  Phase 6: Action Executor                    │
   │  (Executes ONLY if Phase 5 allows)           │
   └──────────────────┬───────────────────────────┘
                      │
                      ▼
            Razorpay Client
            (Test Mode ONLY)
                      │
                      ▼
            Razorpay Test Mode API
            (POST /v1/payment_links)
```

The LLM has zero execution privileges. It cannot call Razorpay APIs, modify transaction states, create payment links, retry payments, send customer messages, or bypass safety rules.

---

## 6. Phase 7 — End-to-End Recovery Pipeline & Outcome Tracking

### Complete End-to-End Orchestration Flow

```text
Razorpay payment.failed
        ↓
Webhook Handler (HMAC-SHA256 Signature Verification)
        ↓
Redis Queue (LPUSH/RPOP FIFO)
        ↓
Webhook Worker (Orchestration Engine)
        ↓
Payment Analysis (Failure Classifier + Customer Context)
        ↓
Gemini Decision Engine (Advisory Recommender)
        ↓
Deterministic Safety Guard (Authoritative Business Rules)
        ↓
Action Executor (Authorized Action Dispatcher)
        ↓
Razorpay Test Mode (POST /v1/payment_links)
        ↓
Transaction State: RECOVERY_PENDING
        ↓
Customer Pays via Recovery Link
        ↓
Razorpay payment.captured
        ↓
Causality Verification (Payment Link ID / Reference ID / Notes)
        ↓
Transaction State: RECOVERED (or CAPTURED if organic)
        ↓
Outcome Tracker & Audit Trail (RetryHistory)
        ↓
Deterministic Metrics (RecoveryMetricsService)
```

### Core Recovery Principles

> **"Payment Link creation is not payment recovery."**
>
> Creating a Razorpay Payment Link transitions a transaction to `RECOVERY_PENDING`. Payment recovery occurs only when the customer successfully pays through the recovery channel and Razorpay emits a verified `payment.captured` event.

> **"RECOVERED means RecoverAI can establish that the successful payment was caused by a RecoverAI recovery action."**
>
> Causality is strictly verified:
> 1. The captured payment contains a `payment_link_id` matching the RecoverAI-generated payment link.
> 2. Or the captured payment contains metadata `notes.transaction_id` or `notes.recovered_by == "RecoverAI"`.
> 3. An organic payment for an order where the customer did not use the recovery action transitions to `CAPTURED`, never `RECOVERED`.

### Deterministic Recovery Metrics

All metrics are calculated deterministically from database state with zero LLM involvement:

- **`revenue_at_risk`**: Sum of `amount` (paise) for eligible failed or recovery-pending transactions that have not been recovered.
- **`recovered_revenue`**: Sum of `amount` (paise) for transactions in `RECOVERED` state.
- **`recovery_rate`**:
  $$\text{recovery\_rate} = \frac{\text{total\_recovered\_transactions}}{\text{eligible\_failed\_transactions}}$$
  If $\text{eligible\_failed\_transactions} == 0$, $\text{recovery\_rate} = 0.0$. Division by zero is strictly guarded.
- **`total_failed_transactions`**: Count of transactions currently in `FAILED` status.
- **`total_recovered_transactions`**: Count of transactions in `RECOVERED` status.
- **`payment_links_created`**: Count of transactions with created payment links.
- **`stopped_transactions`**: Count of transactions in `STOPPED` status.

### End-to-End Audit Trail

Every recovery attempt is fully auditable through extended `RetryHistory` records:
- `recommended_action`: AI advisory recommendation
- `confidence`: AI recommendation confidence score
- `ai_rationale`: AI reasoning (sanitized, zero secrets)
- `safety_decision`: Safety Guard verdict (`APPROVE`, `OVERRIDE`, `STOP`)
- `safety_rule_id`: Specific safety rule triggered
- `final_action`: Authorized recovery action
- `execution_result`: Execution status (`SUCCESS`, `FAILED`, `ACTION_NOT_SUPPORTED`, `STOPPED`)
- `error_code` & `error_message`: Structured failure tracking
- `recovered_amount`: Recovered amount in paise upon verified payment capture
- `recovered_at`: Timestamp when payment capture was verified
