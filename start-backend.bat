@echo off
cd /d %~dp0
call .venv\Scripts\activate.bat
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001
