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

# Check Python dependencies
echo "[1/4] Checking Python dependencies..."
PYTHON_CMD="python3"
if [ -f "venv/bin/python" ]; then
    PYTHON_CMD="venv/bin/python"
fi

# Check if critical Python packages are installed
if ! $PYTHON_CMD -c "import fastapi" 2>/dev/null; then
    echo "❌ ERROR: Python dependencies not installed!"
    echo ""
    echo "Please run:"
    echo "  cd backend"
    echo "  pip install -r requirements.txt"
    echo ""
    echo "Or if using a virtual environment:"
    echo "  python3 -m venv venv"
    echo "  source venv/bin/activate"
    echo "  pip install -r backend/requirements.txt"
    exit 1
fi

# Kill any existing dangling processes on our ports
echo "[2/4] Cleaning up old processes..."
lsof -ti:8000 | xargs kill -9 2>/dev/null
lsof -ti:5173,5174,5175 | xargs kill -9 2>/dev/null

# Start Backend
echo "[3/4] Starting Python Backend Server..."
if [ -f "venv/bin/python" ]; then
    venv/bin/python backend/main.py &
else
    python3 backend/main.py &
fi
BACKEND_PID=$!

# Wait a brief moment for backend to initialize
sleep 2

# Start Frontend
echo "[4/4] Starting Vite React Frontend..."
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
