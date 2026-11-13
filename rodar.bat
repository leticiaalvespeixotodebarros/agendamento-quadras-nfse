@echo off
REM Abre o sistema em http://localhost:8000  (Ctrl+C para parar)
cd /d "%~dp0"
if not exist .venv ( python -m venv .venv && .venv\Scripts\python -m pip install -q -r requirements.txt )
if /i "%1"=="demo" .venv\Scripts\python -m app.demo
start "" http://localhost:8000
.venv\Scripts\python -m uvicorn app.main:app --port 8000
