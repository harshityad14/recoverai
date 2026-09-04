# RecoverAI

AI-Powered Payment Recovery Agent built for the **Razorpay AI Buildathon**.

RecoverAI intelligently analyzes payment failure events in real-time, diagnoses the root failure cause using domain taxonomy and customer context, decides on optimal, policy-safe recovery actions via an LLM Decision Engine with deterministic safety guardrails, and executes automated recovery workflows.

---

## 🏗️ System Architecture

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

## 🚀 Implementation Status & Verified Capabilities

- [x] **Phase 1 — Foundation & Core Infrastructure**: Modular FastAPI backend, PostgreSQL/SQLite with SQLAlchemy, Redis client pool, Pydantic settings management, and health endpoints.
- [x] **Phase 2 — Webhook Ingestion & Verification**: Cryptographic HMAC-SHA256 signature verification against raw body, deduplication via `X-Razorpay-Event-Id`, and Redis queue buffering.
- [x] **Phase 3 — Failure Taxonomy & Customer Context**: Domain-specific classification of Razorpay failure codes into actionable categories (technical, user, business), eligibility checks, and customer history enrichment.
- [x] **Phase 4 — Gemini LLM Decision Engine**: Google Gemini integration (`gemini-3.1-flash-lite`) producing structured Pydantic `RecoveryDecision` objects (action, confidence, rationale, urgency).
- [x] **Phase 5 — Deterministic Safety Guard**: Strict programmatic guardrails validating attempt limits, failure categories, cooldown periods, and maximum allowable actions (`APPROVE`, `OVERRIDE`, `STOP`).
- [x] **Phase 6 — Razorpay Action Executor**: Test Mode execution creating authentic Razorpay Payment Links with attribution metadata, enforcing Test Mode-only keys (`rzp_test_...`).
- [x] **Phase 7 — End-to-End Recovery Pipeline**: Full autonomous orchestration connecting failure events to recovery execution, strict causal attribution on `payment.captured`, and real-time recovery metrics.
- [x] **Phase 8 — Professional Recovery Dashboard**: Light, clean enterprise dashboard inspired by Google Cloud and Stripe design systems with real-time recovery metrics and demo scenario inspection.

---

## 📁 Repository Structure

```text
recoverai/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                     # FastAPI application entrypoint
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py               # Pydantic environment configuration
│   │   │   ├── database.py             # SQLAlchemy engine & session factory
│   │   │   └── redis.py                # Redis client connection factory
│   │   ├── models/
│   │   │   ├── __init__.py
│   │   │   └── base.py                 # SQLAlchemy declarative base & audit fields
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   └── health.py               # Pydantic schemas for health responses
│   │   └── api/
│   │       ├── __init__.py
│   │       └── routes/
│   │           ├── __init__.py
│   │           └── health.py           # GET /health endpoint
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py                 # Pytest test client fixtures
│   │   └── test_health.py              # Health check unit and integration tests
│   ├── pytest.ini                      # Pytest configuration
│   ├── requirements.txt                # Production backend dependencies
│   └── requirements-dev.txt            # Development & testing dependencies
├── frontend/
│   ├── public/
│   ├── src/
│   │   ├── App.jsx                     # RecoverAI status & monitoring dashboard scaffold
│   │   ├── index.css
│   │   └── main.jsx
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   └── .env.example
├── docs/
│   ├── architecture.md                 # Detailed architecture & component definitions
│   └── phase1_setup.md                 # Phase 1 setup and verification guide
├── scripts/
│   ├── run_backend.bat                 # Windows backend runner
│   ├── run_backend.sh                  # Linux/macOS backend runner
│   ├── run_tests.bat                   # Windows test runner
│   ├── run_tests.sh                    # Linux/macOS test runner
│   ├── run_frontend.bat                # Windows frontend runner
│   └── run_frontend.sh                 # Linux/macOS frontend runner
├── .env.example                        # Template environment variables
├── .gitignore                          # Repository ignores
└── README.md                           # Project documentation & architecture
```

---

## ⚙️ Quickstart Guide

### Prerequisites
- **Python**: 3.10+
- **Node.js**: 18+ (for frontend)
- **PostgreSQL & Redis** (optional for Phase 1 health check, required for subsequent phases)

### 1. Backend Setup

```bash
cd backend
python -m venv .venv

# On Windows (PowerShell):
.\.venv\Scripts\Activate.ps1

# On Linux / macOS:
source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Run the Backend

```bash
# Using uvicorn directly:
uvicorn app.main:app --reload --port 8000

# Or using the provided runner script (from repository root):
.\scripts\run_backend.bat
```

Visit the interactive API documentation at:
- Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)
- Health Check: [http://localhost:8000/health](http://localhost:8000/health)

### 3. Run Tests

```bash
# From backend directory:
pytest -v

# Or using the script (from repository root):
.\scripts\run_tests.bat
```

### 4. Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

---

## 🔒 Security & Safety Principles

1. **Deterministic Safety Guards**: Autonomous LLM decisions never execute directly without validating against hard business constraints and recovery rate-limits.
2. **Credential Hygiene**: Strictly zero hardcoded API keys. All keys injected via environment configurations.
3. **Audit Trail**: Every failure event, diagnosis, LLM recommendation, and triggered recovery action is immutably logged to PostgreSQL.
