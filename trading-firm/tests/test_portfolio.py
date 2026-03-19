"""
Portfolio module tests — position validation, HMAC integrity, limits.
"""
from __future__ import annotations

import json
import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")
os.environ.setdefault("PORTFOLIO_HMAC_KEY", "b" * 64)
os.environ.setdefault("STARTING_BALANCE", "1000")
os.environ.setdefault("RISK_PROFILE", "moderate")

from core.portfolio import Portfolio, Position
from core.security import CircuitBreaker


# ---------------------------------------------------------------------------
# Position validation
# ---------------------------------------------------------------------------

def test_position_rejects_invalid_outcome():
    with pytest.raises(ValueError):
        Position(
            market_id="mkt-1",
            question="Will X happen?",
            outcome="MAYBE",
            entry_price=0.5,
            size_usd=10.0,
            shares=20.0,
        )


def test_position_rejects_nan_entry_price():
    with pytest.raises(ValueError):
        Position(
            market_id="mkt-2",
            question="Will Y happen?",
            outcome="YES",
            entry_price=float("nan"),
            size_usd=10.0,
            shares=20.0,
        )


def test_position_rejects_negative_size():
    with pytest.raises(Exception):
        Position(
            market_id="mkt-3",
            question="Will Z happen?",
            outcome="NO",
            entry_price=0.4,
            size_usd=-5.0,
            shares=10.0,
        )


def test_position_rejects_inf_shares():
    with pytest.raises(ValueError):
        Position(
            market_id="mkt-4",
            question="Will W happen?",
            outcome="YES",
            entry_price=0.5,
            size_usd=10.0,
            shares=float("inf"),
        )


# ---------------------------------------------------------------------------
# Portfolio HMAC and persistence
# ---------------------------------------------------------------------------

def _make_portfolio(tmp_path: str) -> Portfolio:
    p = Portfolio()
    p._state_path = tmp_path
    return p


def test_portfolio_saves_and_loads_with_valid_hmac(tmp_path):
    state_file = str(tmp_path / "portfolio_state.json")
    p = Portfolio()
    p._state_path = state_file
    p.save()
    loaded = Portfolio.load(state_file)
    assert abs(loaded.cash - p.cash) < 0.01


def test_portfolio_rejects_tampered_state(tmp_path):
    state_file = str(tmp_path / "portfolio_state.json")
    p = Portfolio()
    p._state_path = state_file
    p.save()

    # Tamper: change balance in the saved file
    with open(state_file) as f:
        payload = json.load(f)
    payload["data"]["cash"] = 999999.0
    with open(state_file, "w") as f:
        json.dump(payload, f)

    loaded = Portfolio.load(state_file)
    # Should start fresh (HMAC mismatch)
    assert loaded.cash == loaded.starting_balance


def test_portfolio_rejects_missing_signature(tmp_path):
    state_file = str(tmp_path / "portfolio_state.json")
    p = Portfolio()
    p._state_path = state_file
    p.save()

    with open(state_file) as f:
        payload = json.load(f)
    del payload["__sig"]
    with open(state_file, "w") as f:
        json.dump(payload, f)

    loaded = Portfolio.load(state_file)
    assert loaded.cash == loaded.starting_balance


def test_portfolio_rejects_implausible_balance(tmp_path):
    state_file = str(tmp_path / "portfolio_state.json")
    p = Portfolio()
    p._state_path = state_file
    p.save()

    # Write a signed state with implausible balance
    from core.security import sign_state
    data = {
        "starting_balance": 1000.0,
        "cash": 10_000_000.0,  # 10000x starting
        "daily_start_equity": 1000.0,
        "equity_history": [],
        "positions": {},
        "closed": [],
    }
    sig = sign_state(data)
    with open(state_file, "w") as f:
        json.dump({"data": data, "__sig": sig}, f)

    loaded = Portfolio.load(state_file)
    assert loaded.cash == loaded.starting_balance  # fresh start


# ---------------------------------------------------------------------------
# Position limits
# ---------------------------------------------------------------------------

def test_can_open_position_respects_max_open(tmp_path, monkeypatch):
    import core.config as cfg_mod
    # Force moderate profile with max_open=10
    os.environ["RISK_PROFILE"] = "moderate"
    cfg_mod._config = None  # reset singleton

    p = Portfolio()
    p.cash = 100_000.0

    # Open 10 positions (at max)
    for i in range(10):
        p._positions[f"mkt-{i}"] = Position(
            market_id=f"mkt-{i}",
            question=f"Q{i}",
            outcome="YES",
            entry_price=0.5,
            size_usd=10.0,
            shares=20.0,
        )

    ok, reason = p.can_open_position(10.0)
    assert not ok
    assert "Max open" in reason


def test_can_open_position_respects_balance():
    p = Portfolio()
    p.cash = 5.0  # only $5 available
    ok, reason = p.can_open_position(10.0)
    assert not ok
    assert "cash" in reason.lower() or "Insufficient" in reason


def test_stop_loss_triggers():
    p = Portfolio()
    p.cash = 1000.0
    p._positions["mkt-sl"] = Position(
        market_id="mkt-sl",
        question="Stop loss test",
        outcome="YES",
        entry_price=0.5,
        size_usd=100.0,
        shares=200.0,
        stop_loss_pct=0.5,  # 50% loss triggers stop
    )
    # Current price drops 60%
    trigger = p.check_stop_loss_take_profit("mkt-sl", current_price=0.2)
    assert trigger == "stop_loss"


def test_take_profit_triggers():
    p = Portfolio()
    p.cash = 1000.0
    p._positions["mkt-tp"] = Position(
        market_id="mkt-tp",
        question="Take profit test",
        outcome="YES",
        entry_price=0.5,
        size_usd=100.0,
        shares=200.0,
        take_profit_pct=0.8,  # 80% gain triggers take-profit
    )
    # At price 0.95: unrealised = (200*0.95 - 100)/100 = 0.9 >= 0.8 → triggers
    trigger = p.check_stop_loss_take_profit("mkt-tp", current_price=0.95)
    assert trigger == "take_profit"


def test_circuit_breaker_halts_at_threshold():
    cb = CircuitBreaker(starting_balance=1000.0, circuit_breaker_pct=25.0)
    with pytest.raises(RuntimeError):
        cb.check(equity=700.0)
