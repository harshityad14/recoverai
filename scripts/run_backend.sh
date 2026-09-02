#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="${SCRIPT_DIR}/../backend"

cd "${BACKEND_DIR}"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
