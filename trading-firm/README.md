# Polymarket Autonomous Trading Firm

An autonomous, production-grade AI trading system that operates on [Polymarket](https://polymarket.com)
prediction markets. A team of specialised AI agents collaborate, debate, and vote on trades —
like a quantitative trading firm run entirely by AI.

> **Disclaimer**: This is experimental software. Prediction markets are speculative instruments.
> Trade only what you can afford to lose. The authors accept no liability for financial losses.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    TRADING FIRM                              │
│                                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐   │
│  │ Analyst  │  │Journalist│  │  Macro   │  │Historian │   │
│  │(Quant)   │  │(News)    │  │(Politics)│  │(BaseRate)│   │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘   │
│       │              │              │              │         │
│       └──────────────┴──────────────┴──────────────┘         │
│                            │                                 │
│                    ┌───────▼───────┐                        │
│                    │  Strategist   │ ◄── weights opinions   │
│                    │ (Orchestrator)│     by agent accuracy  │
│                    └───────┬───────┘                        │
│                            │ consensus                      │
│                    ┌───────▼───────┐                        │
│                    │  Contrarian   │ stress test / veto     │
│                    └───────┬───────┘                        │
│                            │                                │
│                    ┌───────▼───────┐                        │
│                    │ Risk Manager  │ hard limits / gate     │
│                    └───────┬───────┘                        │
│                            │ approved                       │
│                    ┌───────▼───────┐                        │
│                    │  Execution    │ deterministic          │
│                    └───────┬───────┘                        │
│                            │                                │
│                    ┌───────▼───────┐                        │
│                    │  Polymarket   │ paper or live orders   │
│                    └───────────────┘                        │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  Security Agent — scans every market before analysis │   │
│  └─────────────────────────────────────────────────────┘   │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  FastAPI + WebSocket → Next.js Dashboard             │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
```

---

## Agent Team

| Agent | Role |
|---|---|
| **Analyst** | Pure quantitative analysis — volume, pricing, Kelly sizing |
| **Journalist** | Web search for news, sentiment, and recency gaps |
| **Macro** | Macroeconomic and political context |
| **Historian** | Base rates and historical precedents from memory |
| **Security Agent** | Fraud detection, prompt injection, wash trading |
| **Risk Manager** | Hard position limits, concentration, circuit breaker |
| **Contrarian** | Devil's advocate — prevents groupthink, has veto power |
| **Strategist** | Weighted consensus orchestrator, final decision |
| **Execution** | Deterministic order placement (no AI inference) |

---

## Prerequisites

- Python 3.11+
- Node.js 18+ and npm 9+
- A Polygon-compatible wallet (MetaMask recommended)
- USDC on Polygon network (for live trading)
- Anthropic API key ([console.anthropic.com](https://console.anthropic.com))

---

## Getting Polymarket CLOB Credentials

1. Visit [polymarket.com](https://polymarket.com) and connect your wallet
2. Go to your profile → API Keys
3. Generate a new API key — you'll receive:
   - `API_KEY` (starts with a UUID)
   - `API_SECRET`
   - `API_PASSPHRASE`
4. Export your MetaMask private key (never share this):
   - MetaMask → Account Details → Export Private Key
5. Fill in all values in `.env`

---

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url>
cd trading-firm

# 2. Run automated setup
./scripts/setup.sh

# 3. Fill in your API keys in .env

# 4. Start paper trading
./scripts/paper_trade.sh
```

The dashboard opens at **http://localhost:3000**.

---

## Dashboard Guide

- **Main page**: Live agent feed, open positions, equity snapshot
- **Agents page**: Per-agent status, accuracy, pause/resume controls
- **Portfolio page**: Full equity curve, trade log, category P&L
- **Settings page**: Risk profile, emergency stop

---

## Risk Profiles

| Profile | Max Position | Max Open | Circuit Breaker |
|---|---|---|---|
| **Conservative** | $20 | 5 | 15% drawdown |
| **Moderate** | $50 | 10 | 25% drawdown |
| **Aggressive** | $100 | 20 | 40% drawdown |

Example: On **Conservative** with $1,000 starting balance, if equity drops to $850
(15%), the circuit breaker trips and all trading halts until manually reset.

---

## How Consensus Voting Works

1. Four agents (Analyst, Journalist, Macro, Historian) each return an opinion:
   `BUY_YES`, `BUY_NO`, or `SKIP` with a confidence score (0–1).
2. The Strategist weighs each opinion by the agent's **historical accuracy**.
3. Consensus score = `Σ(confidence × accuracy × direction) / Σ(weights)`
   where direction is +1 (BUY_YES), -1 (BUY_NO), 0 (SKIP).
4. If `|consensus_score| < MIN_CONSENSUS_SCORE` (default 0.65): **SKIP**.
5. If agents strongly disagree (high std dev): **SKIP**.
6. Contrarian stress-tests the result — can **veto** if confidence > 0.8 in opposite direction.
7. Risk Manager does final hard-limit checks.
8. Execution places the order.

---

## Circuit Breaker

The circuit breaker compares your current equity to your starting balance.
If the drawdown exceeds `CIRCUIT_BREAKER_PCT`, it trips and:
- All new trades are halted immediately
- A `circuit.breaker` event is broadcast to the dashboard
- The loop pauses (multiplied interval)

**To reset**: Call `GET /config` to check status, then manually edit the portfolio state
and restart the loop, or implement the reset endpoint.

---

## Agent Accuracy Tracking

Every agent's prediction is stored in memory with the market ID.
When a market resolves (price → 0.99+), the system compares each agent's
prediction to the outcome and calls `update_agent_accuracy(agent_id, was_correct)`.

Over time, agents that make better predictions get higher weights in consensus.
Starting accuracy is 0.5 (neutral) for all agents.

---

## Adding a New Agent

1. Create `agents/my_agent.py`
2. Import and extend `BaseAgent`
3. Implement `analyze(market) -> AgentOpinion` and `report() -> str`
4. Add to `main_loop.py` in `TradingFirm.__init__()` and `_analyse_market()`
5. Add to `api/server.py` agent list
6. Write tests in `tests/test_agents.py`

```python
from agents.base_agent import AgentOpinion, BaseAgent

class MyAgent(BaseAgent):
    AGENT_ID = "my_agent"

    def analyze(self, market):
        raw = self._call_claude(MY_SYSTEM_PROMPT, my_prompt(market))
        return self._parse_opinion(raw, market)

    def report(self):
        return f"MyAgent | accuracy={self.accuracy:.2%}"
```

---

## Security Model

See [SECURITY.md](SECURITY.md) for a complete threat model and mitigations.

---

## FAQ

**Q: The system keeps SKIPping every market — is it broken?**
A: No. SKIP is the safe default. The consensus threshold (0.65) and minimum edge (0.05)
are intentionally conservative. Use lower thresholds in `.env` to see more trades,
but understand the risk.

**Q: The circuit breaker tripped. How do I reset it?**
A: Set equity back above threshold in `logs/portfolio_state.json` (after HMAC re-signing),
or restart with a fresh portfolio.

**Q: Can I run without Anthropic API?**
A: No — all agent reasoning requires Claude. You need a valid `ANTHROPIC_API_KEY`.

**Q: How much does each analysis cost in API fees?**
A: Approximately $0.01–$0.05 per market per cycle (4 agent calls + strategist).
At 120s intervals, that's roughly $1–5/day for 10 markets per cycle.

**Q: Is this legal?**
A: Polymarket is a legal prediction market platform. Using automated trading tools
is generally permitted. Verify the terms of service and local regulations.
