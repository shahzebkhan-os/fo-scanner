#!/usr/bin/env bash

echo "=================================================="
echo "    Starting NSE F&O Scanner...                   "
echo "=================================================="

# Function to clean up background processes on exit
cleanup() {
    echo ""
    echo "Shutting down servers..."
    kill $BACKEND_PID $FRONTEND_PID 2>/dev/null
    exit
}

# Trap Ctrl+C (SIGINT) and SIGTERM to run cleanup
trap cleanup INT TERM

# Kill any existing dangling processes on our ports
echo "[1/3] Cleaning up old processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173,5174,5175 | xargs kill -9 2>/dev/null

# Start Backend
echo "[2/3] Starting Python Backend Server..."
# Assuming venv is in the root directory
if [ -f "venv/bin/python" ]; then
    venv/bin/python backend/main.py &
else
    python3 backend/main.py &
fi
BACKEND_PID=$!

# Wait a brief moment for backend to initialize
sleep 2

# Start Frontend
echo "[3/3] Starting Vite React Frontend..."
cd frontend
npm run dev -- --port 5175 &
FRONTEND_PID=$!
cd ..

echo ""
echo "=================================================="
echo "✅ Everything is running!"
echo "   Backend API: http://localhost:8000"
echo "   Frontend UI: http://localhost:5175"
echo ""
echo "   Press Ctrl+C to stop both servers."
echo "=================================================="

# Wait indefinitely for background processes
wait
