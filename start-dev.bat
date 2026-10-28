@echo off
echo Starting Multi-Agent Codebase Navigator...
start "Backend (FastAPI)" cmd /k "cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
start "Frontend (Vite)" cmd /k "cd frontend && npm run dev"
echo Backend and Frontend dev servers have been launched in separate windows.
pause

