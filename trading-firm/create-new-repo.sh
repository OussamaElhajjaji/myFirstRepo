#!/bin/bash
# create-new-repo.sh
# Run this on your LOCAL machine to create a standalone GitHub repo
# for the polymarket trading firm.
#
# Prerequisites: git, gh (GitHub CLI — https://cli.github.com)
#
# Usage:
#   chmod +x create-new-repo.sh
#   ./create-new-repo.sh

set -e

REPO_NAME="polymarket-trading-firm"
DESCRIPTION="Autonomous AI trading firm for Polymarket prediction markets"

echo "Step 1: Cloning source repo..."
git clone https://github.com/OussamaElhajjaji/myFirstRepo.git /tmp/myFirstRepo-clone
cd /tmp/myFirstRepo-clone

echo "Step 2: Creating new GitHub repo..."
gh repo create "$REPO_NAME" \
  --description "$DESCRIPTION" \
  --public \
  --confirm 2>/dev/null || \
gh repo create "OussamaElhajjaji/$REPO_NAME" \
  --description "$DESCRIPTION" \
  --public

echo "Step 3: Extracting trading-firm as standalone repo..."
cd /tmp
cp -r /tmp/myFirstRepo-clone/trading-firm /tmp/$REPO_NAME
cd /tmp/$REPO_NAME

git init -b main
git add -A
git commit -m "Initial commit: Polymarket Autonomous AI Trading Firm

A fully autonomous, production-grade AI trading firm on Polymarket.
9 specialised AI agents collaborate, debate, and vote on trades.

Features:
- 9 AI agents (Analyst, Journalist, Macro, Historian, Security, Risk Manager, Contrarian, Strategist, Execution)
- Weighted consensus voting by agent historical accuracy
- HMAC-signed portfolio state with circuit breaker
- FastAPI + WebSocket real-time event streaming
- Next.js 14 dark terminal dashboard
- 55 tests (100% passing), all external APIs mocked
- Paper trading by default, live trading with full confirmation flow"

echo "Step 4: Pushing to GitHub..."
git remote add origin "https://github.com/OussamaElhajjaji/$REPO_NAME.git"
git push -u origin main

echo ""
echo "Done! Your new repo is at:"
echo "  https://github.com/OussamaElhajjaji/$REPO_NAME"
echo ""
echo "To get started:"
echo "  cd /tmp/$REPO_NAME"
echo "  ./scripts/setup.sh"
