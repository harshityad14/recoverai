# Phase 1 Setup & Verification Guide

## Summary
Phase 1 establishes the structural and architectural foundation for RecoverAI:
- FastAPI backend with typed settings
- PostgreSQL connection via SQLAlchemy
- Redis connection utilities
- Initial database declarative configuration and base model mixins
- React frontend scaffold with live health status monitoring
- Complete test suite verifying `GET /health` and root endpoints
- Clean repository layout, `.env.example`, and operational scripts

---

## Environment Verification

### Prerequisites
- Python 3.10+
- Node.js 18+

### Setup Commands
```bash
# 1. Backend
cd backend
python -m venv .venv

# On Windows:
.\.venv\Scripts\Activate.ps1
# On Linux/macOS:
source .venv/bin/activate

pip install -r requirements-dev.txt

# 2. Run Tests
pytest -v

# 3. Run Backend Application
uvicorn app.main:app --port 8000 --reload
```

---

## Testing Verification
Run backend unit tests to ensure that the health endpoint conforms to contract:
```bash
cd backend
python -m pytest -v
```
Expected output:
- `test_health_check_status_code` PASSED
- `test_health_check_payload_structure` PASSED
- `test_api_v1_health_check` PASSED
- `test_root_endpoint` PASSED
