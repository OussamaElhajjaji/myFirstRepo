"""
FastAPI server with REST endpoints and WebSocket live feed.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Set

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.config import get_config
from core.logger import get_logger, scrub_secrets
from core.messaging import ALL_TOPICS, get_bus
from core.portfolio import Portfolio

logger = get_logger("api")

app = FastAPI(title="Polymarket Trading Firm API", version="1.0.0")

# CORS — allow dashboard at localhost:3000 only
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# Request logging middleware with secret scrubbing
# ---------------------------------------------------------------------------


@app.middleware("http")
async def log_requests(request: Any, call_next: Any) -> Any:
    path = scrub_secrets(str(request.url.path))
    logger.info("HTTP %s %s", request.method, path)
    response = await call_next(request)
    return response


# ---------------------------------------------------------------------------
# WebSocket connection manager
# ---------------------------------------------------------------------------


class ConnectionManager:
    """Manages active WebSocket connections."""

    def __init__(self) -> None:
        self._connections: Set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self._connections.add(ws)
        logger.info("WebSocket connected (%d total)", len(self._connections))

    def disconnect(self, ws: WebSocket) -> None:
        self._connections.discard(ws)
        logger.info("WebSocket disconnected (%d remaining)", len(self._connections))

    async def broadcast(self, message: dict) -> None:
        dead: List[WebSocket] = []
        for ws in list(self._connections):
            try:
                await ws.send_text(json.dumps(message, default=str))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self._connections.discard(ws)


_manager = ConnectionManager()

# Subscribe bus events to WebSocket broadcast
def _make_bus_handler(manager: ConnectionManager) -> Any:
    def handler(topic: str, payload: dict) -> None:
        asyncio.create_task(manager.broadcast({"topic": topic, "payload": payload}))
    return handler


@app.on_event("startup")
async def _startup() -> None:
    bus = get_bus()
    handler = _make_bus_handler(_manager)
    for topic in ALL_TOPICS:
        bus.subscribe(topic, handler)
    logger.info("API server started — bus subscribed to %d topics", len(ALL_TOPICS))


# ---------------------------------------------------------------------------
# Helper to get the trading firm singleton (lazy import to avoid circular)
# ---------------------------------------------------------------------------

def _get_firm():
    from main_loop import get_firm
    return get_firm()


def _get_portfolio() -> Portfolio:
    try:
        return _get_firm().portfolio
    except Exception:
        return Portfolio.load()


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
async def health() -> dict:
    cfg = get_config()
    return {
        "status": "ok",
        "paper_trading": cfg.paper_trading,
        "risk_profile": cfg.risk_profile.name,
    }


@app.get("/portfolio")
async def get_portfolio_state() -> dict:
    p = _get_portfolio()
    return {
        "equity": p.equity,
        "cash": p.cash,
        "total_invested": p.total_invested,
        "total_pnl": p.total_pnl,
        "daily_pnl": p.daily_pnl,
        "win_rate": p.win_rate,
        "sharpe_ratio": p.sharpe_ratio,
        "open_positions": [
            {
                "market_id": pos.market_id,
                "question": pos.question[:80],
                "outcome": pos.outcome,
                "entry_price": pos.entry_price,
                "size_usd": pos.size_usd,
                "shares": pos.shares,
                "category": pos.category,
                "opened_at": pos.opened_at,
                "agent_memo": pos.agent_memo[:100],
            }
            for pos in p.open_positions
        ],
    }


@app.get("/portfolio/history")
async def portfolio_history(limit: int = 100) -> dict:
    p = _get_portfolio()
    return {
        "equity_history": p._equity_history[-limit:],
        "closed_positions": [
            {
                "market_id": pos.market_id,
                "question": pos.question[:80],
                "outcome": pos.outcome,
                "entry_price": pos.entry_price,
                "exit_price": pos.exit_price,
                "pnl": pos.pnl,
                "opened_at": pos.opened_at,
                "closed_at": pos.closed_at,
            }
            for pos in p.closed_positions[-limit:]
        ],
    }


@app.get("/portfolio/metrics")
async def portfolio_metrics() -> dict:
    p = _get_portfolio()
    closed = p.closed_positions
    wins = [pos.pnl for pos in closed if pos.pnl > 0]
    losses = [pos.pnl for pos in closed if pos.pnl <= 0]
    drawdowns = []
    peak = p.starting_balance
    for eq in p._equity_history:
        if eq > peak:
            peak = eq
        if peak > 0:
            drawdowns.append((peak - eq) / peak)
    max_drawdown = max(drawdowns, default=0.0)

    return {
        "total_pnl": p.total_pnl,
        "win_rate": p.win_rate,
        "avg_win": sum(wins) / len(wins) if wins else 0.0,
        "avg_loss": sum(losses) / len(losses) if losses else 0.0,
        "sharpe_ratio": p.sharpe_ratio,
        "max_drawdown": max_drawdown,
        "total_trades": len(closed),
    }


@app.get("/agents")
async def get_agents() -> dict:
    try:
        firm = _get_firm()
        agents = [
            firm.analyst,
            firm.journalist,
            firm.macro,
            firm.historian,
            firm.risk_manager,
            firm.contrarian,
            firm.strategist,
            firm.security_agent,
            firm.execution,
        ]
        return {"agents": [a.get_status() for a in agents]}
    except Exception:
        return {"agents": []}


@app.get("/agents/{agent_id}/memory")
async def get_agent_memory(agent_id: str, limit: int = 20) -> dict:
    from core.memory import Memory
    from core.config import get_config
    cfg = get_config()
    memory = Memory(f"{cfg.log_dir}/memory.db")
    items = memory.recall_recent(agent_id, limit=limit)
    return {
        "agent_id": agent_id,
        "memories": [{"key": k, "value": v} for k, v in items],
    }


@app.get("/markets")
async def get_markets() -> dict:
    from core.polymarket import PolymarketClient
    client = PolymarketClient()
    markets = client.get_markets(limit=20)
    return {
        "markets": [
            {
                "id": m.id,
                "question": m.question[:100],
                "yes_price": m.yes_price,
                "no_price": m.no_price,
                "volume": m.volume,
                "liquidity": m.liquidity,
                "days_to_end": m.days_to_end,
                "category": m.category,
            }
            for m in markets
        ]
    }


@app.get("/config")
async def get_config_endpoint() -> dict:
    cfg = get_config()
    return {
        "paper_trading": cfg.paper_trading,
        "risk_profile": cfg.risk_profile.name,
        "max_position_usd": cfg.max_position_usd,
        "max_open_positions": cfg.max_open_positions,
        "circuit_breaker_pct": cfg.circuit_breaker_pct,
        "loop_interval_sec": cfg.loop_interval_sec,
        "min_edge_threshold": cfg.min_edge_threshold,
        "min_consensus_score": cfg.min_consensus_score,
    }


class RiskProfileRequest(BaseModel):
    profile: str


@app.post("/config/risk-profile")
async def set_risk_profile(req: RiskProfileRequest) -> dict:
    from core.config import RISK_PROFILES
    if req.profile not in RISK_PROFILES:
        raise HTTPException(status_code=400, detail=f"Invalid profile: {req.profile}")
    import os
    os.environ["RISK_PROFILE"] = req.profile
    return {"profile": req.profile, "message": "Risk profile updated (restart to persist)"}


@app.post("/agents/{agent_id}/pause")
async def pause_agent(agent_id: str) -> dict:
    try:
        firm = _get_firm()
        agent = _find_agent(firm, agent_id)
        agent.pause()
        return {"agent_id": agent_id, "paused": True}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@app.post("/agents/{agent_id}/resume")
async def resume_agent(agent_id: str) -> dict:
    try:
        firm = _get_firm()
        agent = _find_agent(firm, agent_id)
        agent.resume()
        return {"agent_id": agent_id, "paused": False}
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Agent {agent_id} not found")


@app.post("/trading/pause")
async def pause_trading() -> dict:
    _get_firm().pause()
    return {"paused": True}


@app.post("/trading/resume")
async def resume_trading() -> dict:
    _get_firm().resume()
    return {"paused": False}


class EmergencyStopRequest(BaseModel):
    confirm: str


@app.post("/trading/emergency-stop")
async def emergency_stop(req: EmergencyStopRequest) -> dict:
    if req.confirm != "STOP":
        raise HTTPException(status_code=400, detail="Confirmation required: send {\"confirm\": \"STOP\"}")

    firm = _get_firm()
    firm.pause()

    # Cancel all open orders
    client = PolymarketClient() if True else None
    open_orders = firm.polymarket.get_open_orders()
    for order in open_orders:
        order_id = order.get("id", order.get("orderID", ""))
        if order_id:
            firm.polymarket.cancel_order(order_id)

    logger.critical("EMERGENCY STOP triggered via API")
    get_bus().publish("circuit.breaker", {"reason": "Emergency stop via API"})

    return {"stopped": True, "message": "All trading paused and open orders cancelled."}


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------


@app.websocket("/live")
async def websocket_endpoint(ws: WebSocket) -> None:
    await _manager.connect(ws)

    # Send initial state on connect
    try:
        p = _get_portfolio()
        await ws.send_text(json.dumps({
            "topic": "initial_state",
            "payload": {
                "equity": p.equity,
                "cash": p.cash,
                "open_positions": len(p.open_positions),
                "paper_trading": get_config().paper_trading,
            },
        }, default=str))

        # Keep connection alive
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                # Send heartbeat
                await ws.send_text(json.dumps({"topic": "heartbeat", "payload": {}}))
    except WebSocketDisconnect:
        _manager.disconnect(ws)
    except Exception as exc:
        logger.error("WebSocket error: %s", exc)
        _manager.disconnect(ws)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_agent(firm: Any, agent_id: str) -> Any:
    """Find an agent by ID from the firm."""
    agent_map = {
        a.agent_id: a
        for a in [
            firm.analyst, firm.journalist, firm.macro, firm.historian,
            firm.risk_manager, firm.contrarian, firm.strategist,
            firm.security_agent, firm.execution,
        ]
    }
    if agent_id not in agent_map:
        raise KeyError(agent_id)
    return agent_map[agent_id]


from core.polymarket import PolymarketClient  # noqa: E402 — deferred to avoid circular
