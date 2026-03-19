#!/bin/bash
# setup.sh — Fully automated trading firm setup
set -e

# --- Colours ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

check() { echo -e "${GREEN}✓${NC} $1"; }
warn()  { echo -e "${YELLOW}⚠${NC}  $1"; }
fail()  { echo -e "${RED}✗${NC} $1"; exit 1; }

echo -e "${CYAN}"
echo "  ╔═══════════════════════════════════════╗"
echo "  ║   POLYMARKET TRADING FIRM — SETUP     ║"
echo "  ╚═══════════════════════════════════════╝"
echo -e "${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_DIR"

# --- 1. Check Python >= 3.11 ---
if ! command -v python3 &>/dev/null; then
    fail "Python3 not found. Install Python 3.11+."
fi
PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)
if [ "$PYTHON_MAJOR" -lt 3 ] || ([ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 11 ]); then
    fail "Python 3.11+ required, found $PYTHON_VERSION"
fi
check "Python $PYTHON_VERSION"

# --- 2. Check Node >= 18 ---
if ! command -v node &>/dev/null; then
    warn "Node.js not found — dashboard will not be available."
    NODE_OK=false
else
    NODE_VERSION=$(node --version | sed 's/v//' | cut -d. -f1)
    if [ "$NODE_VERSION" -lt 18 ]; then
        warn "Node.js 18+ recommended, found $(node --version)"
        NODE_OK=false
    else
        check "Node.js $(node --version)"
        NODE_OK=true
    fi
fi

# --- 3. Check npm >= 9 ---
if $NODE_OK; then
    NPM_VERSION=$(npm --version | cut -d. -f1)
    if [ "$NPM_VERSION" -lt 9 ]; then
        warn "npm 9+ recommended, found $(npm --version)"
    else
        check "npm $(npm --version)"
    fi
fi

# --- 4. Create virtual environment ---
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
source .venv/bin/activate
check "Python virtual environment"

# --- 5. Install Python dependencies ---
pip install -q --upgrade pip
pip install -q -r requirements.txt
check "Python dependencies installed"

# --- 6. Install dashboard dependencies ---
if $NODE_OK && [ -d "dashboard" ] && [ -f "dashboard/package.json" ]; then
    (cd dashboard && npm install --silent)
    check "Dashboard (Next.js) dependencies installed"
else
    warn "Skipping dashboard setup (Node.js not available or no package.json)"
fi

# --- 7. Set up .env ---
if [ ! -f ".env" ]; then
    cp .env.example .env
    warn ".env created from .env.example — please fill in your API keys"
else
    check ".env file exists"
fi

# --- 8. Generate PORTFOLIO_HMAC_KEY ---
if ! grep -q "^PORTFOLIO_HMAC_KEY=" .env 2>/dev/null || grep -q "^PORTFOLIO_HMAC_KEY=$" .env 2>/dev/null; then
    HMAC_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    echo "PORTFOLIO_HMAC_KEY=$HMAC_KEY" >> .env
    check "PORTFOLIO_HMAC_KEY generated and appended to .env"
else
    check "PORTFOLIO_HMAC_KEY already set"
fi

# --- 9. Create logs directory ---
mkdir -p logs
chmod 700 logs
check "logs/ directory created (mode 700)"

# --- 10. Secure .env ---
chmod 600 .env
check ".env permissions set to 600"

# --- 11. Run tests ---
echo ""
echo -e "${CYAN}Running test suite...${NC}"
if python3 -m pytest tests/ -v --tb=short 2>&1; then
    check "All tests passed"
else
    warn "Some tests failed — check output above"
fi

# --- 12. Summary ---
echo ""
echo -e "${CYAN}══════════════════════════════════════════${NC}"
echo -e "${GREEN}  Setup complete!${NC}"
echo -e "${CYAN}══════════════════════════════════════════${NC}"

# Check for placeholder values
MISSING=()
while IFS='=' read -r key value; do
    [[ "$key" =~ ^#.*$ ]] && continue
    [[ -z "$key" ]] && continue
    if [[ "$value" == *"your_"* ]] || [[ "$value" == *"_here"* ]]; then
        MISSING+=("$key")
    fi
done < .env

if [ ${#MISSING[@]} -gt 0 ]; then
    echo ""
    warn "The following .env values still need to be filled in:"
    for k in "${MISSING[@]}"; do
        echo -e "    ${YELLOW}$k${NC}"
    done
fi

echo ""
echo -e "  Run: ${GREEN}./scripts/paper_trade.sh${NC} to start paper trading"
echo -e "  Run: ${GREEN}./scripts/live_trade.sh${NC} to start live trading"
echo ""
