#!/bin/bash
# live_trade.sh — Start the trading firm in LIVE mode
# WARNING: Real USDC will be spent on Polygon network.
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
fi

# Check required env vars
REQUIRED_VARS=(
    "ANTHROPIC_API_KEY"
    "POLYMARKET_PRIVATE_KEY"
    "POLYMARKET_API_KEY"
    "POLYMARKET_API_SECRET"
    "POLYMARKET_API_PASSPHRASE"
    "WALLET_ADDRESS"
    "PORTFOLIO_HMAC_KEY"
    "STARTING_BALANCE"
)

MISSING=()
for var in "${REQUIRED_VARS[@]}"; do
    val=$(grep "^${var}=" .env 2>/dev/null | cut -d= -f2 | tr -d '"')
    if [ -z "$val" ] || [[ "$val" == *"your_"* ]]; then
        MISSING+=("$var")
    fi
done

if [ ${#MISSING[@]} -gt 0 ]; then
    echo "ERROR: The following required environment variables are not set:"
    for v in "${MISSING[@]}"; do
        echo "  - $v"
    done
    echo "Set them in .env before running live trading."
    exit 1
fi

STARTING_BALANCE=$(grep "^STARTING_BALANCE=" .env | cut -d= -f2 | tr -d '"')

echo "================================================================"
echo "  WARNING: LIVE TRADING MODE"
echo "  Real USDC will be spent on Polygon network"
echo "  Starting balance: \$$STARTING_BALANCE"
echo "================================================================"
sleep 3

read -p "Enter your starting balance to confirm (\$$STARTING_BALANCE): " confirm_balance
if [ "$confirm_balance" != "$STARTING_BALANCE" ]; then
    echo "Balance mismatch. Aborting."
    exit 1
fi

read -p "Type LIVE to confirm you want to start live trading: " confirm_word
if [ "$confirm_word" != "LIVE" ]; then
    echo "Confirmation failed. Aborting."
    exit 1
fi

# Set live mode in environment
export PAPER_TRADING=False

echo "Starting in 5 seconds... Press Ctrl+C to abort."
sleep 5

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

echo "Starting API server on port 8000..."
python3 -m uvicorn api.server:app --port 8000 &
API_PID=$!

if [ -d "dashboard" ] && [ -f "dashboard/package.json" ]; then
    echo "Starting dashboard on port 3000..."
    (cd dashboard && npm run dev 2>/dev/null) &
    DASH_PID=$!
fi

echo "Starting LIVE trading loop..."
python3 main_loop.py &
LOOP_PID=$!

sleep 3

if command -v xdg-open &>/dev/null; then
    xdg-open http://localhost:3000 2>/dev/null || true
elif command -v open &>/dev/null; then
    open http://localhost:3000 2>/dev/null || true
fi

echo ""
echo "================================================"
echo "  LIVE TRADING IS ACTIVE"
echo "  Dashboard: http://localhost:3000"
echo "  API:       http://localhost:8000"
echo "  Press Ctrl+C to stop all processes."
echo "================================================"
echo ""

wait
