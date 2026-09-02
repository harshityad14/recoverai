@echo off
echo Starting RecoverAI FastAPI Backend...
cd /d "%~dp0\..\backend"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
