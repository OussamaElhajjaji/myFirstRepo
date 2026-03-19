#!/bin/bash
# paper_trade.sh — Start the trading firm in paper trading mode
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# Activate virtual environment if it exists
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Verify paper trading mode
if [ -f ".env" ]; then
    PAPER=$(grep "^PAPER_TRADING=" .env | cut -d= -f2 | tr -d '"' | tr '[:upper:]' '[:lower:]')
    if [ "$PAPER" = "false" ]; then
        echo "ERROR: PAPER_TRADING is set to False in .env"
        echo "Use ./scripts/live_trade.sh for live trading."
        exit 1
    fi
fi
echo "Paper trading mode confirmed."

# Kill function
cleanup() {
    echo ""
    echo "Shutting down all processes..."
    kill "$API_PID" "$LOOP_PID" 2>/dev/null || true
    if [ -n "$DASH_PID" ]; then
        kill "$DASH_PID" 2>/dev/null || true
    fi
    echo "All processes stopped."
    exit 0
}
trap cleanup SIGINT SIGTERM

# Start FastAPI
echo "Starting API server on port 8000..."
python3 -m uvicorn api.server:app --port 8000 --reload &
API_PID=$!

# Start Next.js dashboard if available
if [ -d "dashboard" ] && [ -f "dashboard/package.json" ]; then
    echo "Starting dashboard on port 3000..."
    (cd dashboard && npm run dev 2>/dev/null) &
    DASH_PID=$!
fi

# Start trading loop
echo "Starting trading loop..."
python3 main_loop.py &
LOOP_PID=$!

# Wait for services to start
sleep 3

# Open browser
if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:3000 2>/dev/null || true
elif command -v open &>/dev/null; then
    open http://localhost:3000 2>/dev/null || true
fi

echo ""
echo "================================================"
echo "  Polymarket Trading Firm is running!"
echo "  Dashboard: http://localhost:3000"
echo "  API:       http://localhost:8000"
echo "  Mode:      PAPER TRADING"
echo "  Press Ctrl+C to stop all processes."
echo "================================================"
echo ""

# Wait for all background processes
wait
