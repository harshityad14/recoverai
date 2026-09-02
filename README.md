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

## 🚀 Phase 1 Implementation Scope

- [x] **Project Structure**: Modular layout for FastAPI backend, PostgreSQL, Redis, React frontend, test suite, and operational scripts.
- [x] **Configuration**: Typed settings management via Pydantic (`pydantic-settings`), `.env`, `.env.example`, and `.gitignore`.
- [x] **FastAPI Core**: FastAPI application featuring `GET /health` with system status and connectivity diagnostics.
- [x] **PostgreSQL with SQLAlchemy**: Database engine, session maker, declarative base, and connection handling.
- [x] **Redis Connection**: Redis client connection pool and status checking utilities.
- [x] **Initial Database Models Base**: Declarative Base with timestamped common schema ready for future entities.
- [x] **Testing Framework**: Comprehensive test suite using `pytest` and `httpx` / `TestClient` for `/health` verification.
- [x] **Scripts**: Cross-platform startup and test runners for Windows and Unix.

> **Note on Constraints**: Webhook processing, LLM decision engines, live Razorpay integrations, and payment execution actions are deferred to subsequent phases in strict adherence to buildathon phase boundaries.

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
