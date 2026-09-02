@echo off
echo Running RecoverAI Test Suite...
cd /d "%~dp0\..\backend"

if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
)

python -m pytest -v
