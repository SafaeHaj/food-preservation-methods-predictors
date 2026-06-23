#!/usr/bin/env bash
set -e

echo "============================================"
echo " Food Research Platform - Local Setup"
echo "============================================"

# --- Backend ---
echo ""
echo "[1/4] Setting up backend..."
cd backend

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created backend/.env — please add your ANTHROPIC_API_KEY"
fi

if [ ! -d venv ]; then
  python3 -m venv venv
fi

source venv/bin/activate
pip install -r requirements.txt -q
echo "Backend dependencies installed."

uvicorn app.main:app --reload --port 8000 &
BACKEND_PID=$!
echo "Backend started (PID $BACKEND_PID) at http://localhost:8000"

cd ..

# --- Frontend ---
echo ""
echo "[2/4] Setting up frontend..."
cd frontend

npm install --silent
npm run dev &
FRONTEND_PID=$!
echo "Frontend started (PID $FRONTEND_PID) at http://localhost:5173"

cd ..

echo ""
echo "============================================"
echo " Platform is running!"
echo " Frontend : http://localhost:5173"
echo " Backend  : http://localhost:8000"
echo " API docs : http://localhost:8000/docs"
echo "============================================"
echo ""
echo "Press Ctrl+C to stop both servers."

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" SIGINT SIGTERM
wait
