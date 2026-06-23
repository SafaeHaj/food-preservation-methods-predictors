@echo off
echo ============================================
echo  Food Research Platform - Local Setup
echo ============================================

REM --- Check Node.js ---
where node >nul 2>&1
if errorlevel 1 (
    echo.
    echo [ERROR] Node.js is not installed or not in PATH.
    echo.
    echo Please install Node.js LTS from:  https://nodejs.org
    echo Then re-run this script.
    echo.
    pause
    exit /b 1
)
for /f "delims=" %%i in ('node --version') do set NODE_VER=%%i
echo Node.js: %NODE_VER%

REM --- Backend ---
echo.
echo [1/4] Setting up backend...
cd backend

if not exist .env (
    copy .env.example .env >nul
    echo Created backend\.env - IMPORTANT: edit it and add your ANTHROPIC_API_KEY
)

if not exist venv (
    echo Creating Python virtual environment...
    python -m venv venv
)

call venv\Scripts\activate.bat
echo Installing backend packages...
pip install -r requirements.txt --quiet
echo Backend ready.

REM Start backend in new window
start "FRP Backend :8000" cmd /k "cd /d %~dp0backend && call venv\Scripts\activate.bat && uvicorn app.main:app --reload --port 8000"
echo Backend starting at http://localhost:8000

cd ..

REM --- Frontend ---
echo.
echo [2/4] Setting up frontend...
cd frontend

if not exist node_modules (
    echo Installing frontend packages (this takes ~1 min first time)...
    npm install
)

REM Start frontend in new window
start "FRP Frontend :5173" cmd /k "cd /d %~dp0frontend && npm run dev"
echo Frontend starting at http://localhost:5173

cd ..

echo.
echo ============================================
echo  Platform starting up!
echo.
echo  Frontend : http://localhost:5173
echo  Backend  : http://localhost:8000
echo  API docs : http://localhost:8000/docs
echo ============================================
echo.
echo Two windows opened: backend and frontend.
echo Close them to stop the servers.
echo.
pause
