"""
Portfolio state management with HMAC integrity, atomic writes,
stop-loss/take-profit monitoring, and Sharpe ratio tracking.
"""
from __future__ import annotations

import json
import math
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional

from core.config import get_config
from core.logger import get_logger
from core.security import (
    sign_state,
    validate_outcome,
    validate_price,
    validate_usd_amount,
    verify_state,
)

logger = get_logger("portfolio")

_NOW = lambda: datetime.now(timezone.utc).isoformat()  # noqa: E731


# ---------------------------------------------------------------------------
# Position dataclass
# ---------------------------------------------------------------------------


@dataclass
class Position:
    """A single open or closed prediction market position."""

    market_id: str
    question: str
    outcome: str          # "YES" or "NO"
    entry_price: float
    size_usd: float       # USD invested
    shares: float         # number of shares
    category: str = ""
    opened_at: str = field(default_factory=_NOW)
    closed_at: Optional[str] = None
    exit_price: Optional[float] = None
    pnl: float = 0.0
    stop_loss_pct: float = 0.5    # exit if unrealised loss > 50%
    take_profit_pct: float = 2.0  # exit if unrealised gain > 100%
    order_id: str = ""
    agent_memo: str = ""

    def __post_init__(self) -> None:
        validate_outcome(self.outcome)
        if math.isnan(self.entry_price) or math.isinf(self.entry_price):
            raise ValueError("entry_price must be finite")
        validate_price(self.entry_price)
        if self.size_usd < 0:
            raise ValueError("size_usd must be non-negative")
        validate_usd_amount(self.size_usd)
        if math.isinf(self.shares):
            raise ValueError("shares must be finite")
        if self.shares < 0:
            raise ValueError("shares must be non-negative")

    @property
    def is_open(self) -> bool:
        return self.closed_at is None

    def unrealised_pnl(self, current_price: float) -> float:
        """Compute unrealised P&L given current market price."""
        if not self.is_open:
            return self.pnl
        current_value = self.shares * current_price
        cost = self.size_usd
        return float(Decimal(str(current_value)) - Decimal(str(cost)))

    def unrealised_pct(self, current_price: float) -> float:
        """Unrealised P&L as percentage of cost."""
        if self.size_usd == 0:
            return 0.0
        return self.unrealised_pnl(current_price) / self.size_usd


# ---------------------------------------------------------------------------
# Portfolio
# ---------------------------------------------------------------------------

_STATE_FILE = "logs/portfolio_state.json"
_IMPLAUSIBLE_MULTIPLIER = 10.0


@dataclass
class Portfolio:
    """Manages positions, cash, and persistent state."""

    starting_balance: float = 1000.0
    cash: float = 0.0  # USDC available
    _positions: Dict[str, Position] = field(default_factory=dict, repr=False)
    _closed: List[Position] = field(default_factory=list, repr=False)
    _daily_start_equity: float = 0.0
    _equity_history: List[float] = field(default_factory=list, repr=False)
    _state_path: str = _STATE_FILE

    def __post_init__(self) -> None:
        cfg = get_config()
        if self.starting_balance == 1000.0:
            self.starting_balance = cfg.starting_balance
        if self.cash == 0.0:
            self.cash = self.starting_balance
        self._daily_start_equity = self.cash

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def open_positions(self) -> List[Position]:
        return list(self._positions.values())

    @property
    def closed_positions(self) -> List[Position]:
        return list(self._closed)

    @property
    def total_invested(self) -> float:
        return sum(p.size_usd for p in self._positions.values())

    @property
    def equity(self) -> float:
        """Cash + current market value of open positions (at entry price as proxy)."""
        position_value = sum(p.shares * p.entry_price for p in self._positions.values())
        return self.cash + position_value

    @property
    def total_pnl(self) -> float:
        closed_pnl = sum(p.pnl for p in self._closed)
        return closed_pnl + (self.equity - self.starting_balance - closed_pnl)

    @property
    def daily_pnl(self) -> float:
        return self.equity - self._daily_start_equity

    @property
    def win_rate(self) -> float:
        wins = sum(1 for p in self._closed if p.pnl > 0)
        total = len(self._closed)
        return wins / total if total > 0 else 0.0

    @property
    def sharpe_ratio(self) -> float:
        """Approximate Sharpe ratio from equity history (0 if insufficient data)."""
        if len(self._equity_history) < 2:
            return 0.0
        returns = [
            (self._equity_history[i] - self._equity_history[i - 1]) / self._equity_history[i - 1]
            for i in range(1, len(self._equity_history))
            if self._equity_history[i - 1] > 0
        ]
        if not returns:
            return 0.0
        mean_r = sum(returns) / len(returns)
        variance = sum((r - mean_r) ** 2 for r in returns) / len(returns)
        std_r = math.sqrt(variance) if variance > 0 else 0.0
        return (mean_r / std_r) * math.sqrt(365) if std_r > 0 else 0.0

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def can_open_position(self, size_usd: float) -> tuple[bool, str]:
        """Check if a new position can be opened."""
        cfg = get_config()
        if len(self._positions) >= cfg.max_open_positions:
            return False, f"Max open positions ({cfg.max_open_positions}) reached"
        if size_usd > self.cash:
            return False, f"Insufficient cash: need ${size_usd:.2f}, have ${self.cash:.2f}"
        if size_usd > cfg.max_position_usd:
            return False, f"Position size ${size_usd:.2f} exceeds max ${cfg.max_position_usd:.2f}"
        return True, "OK"

    def open_position(
        self,
        market_id: str,
        question: str,
        outcome: str,
        entry_price: float,
        size_usd: float,
        category: str = "",
        order_id: str = "",
        agent_memo: str = "",
    ) -> Position:
        """Open a new position, deducting from cash."""
        ok, reason = self.can_open_position(size_usd)
        if not ok:
            raise RuntimeError(f"Cannot open position: {reason}")

        shares = size_usd / entry_price if entry_price > 0 else 0.0
        pos = Position(
            market_id=market_id,
            question=question,
            outcome=outcome,
            entry_price=entry_price,
            size_usd=size_usd,
            shares=shares,
            category=category,
            order_id=order_id,
            agent_memo=agent_memo,
        )
        self._positions[market_id] = pos
        self.cash -= size_usd
        self._equity_history.append(self.equity)
        self.save()
        logger.info("Opened position: %s %s $%.2f @ %.3f", outcome, market_id, size_usd, entry_price)
        return pos

    def close_position(
        self,
        market_id: str,
        exit_price: float,
        reason: str = "",
    ) -> Optional[Position]:
        """Close an open position and return it."""
        pos = self._positions.pop(market_id, None)
        if pos is None:
            logger.warning("close_position: market_id %s not found", market_id)
            return None

        exit_value = pos.shares * exit_price
        pnl = exit_value - pos.size_usd
        pos.exit_price = exit_price
        pos.pnl = pnl
        pos.closed_at = _NOW()
        self.cash += exit_value
        self._closed.append(pos)
        self._equity_history.append(self.equity)
        self.save()
        logger.info(
            "Closed position: %s %s @ %.3f (P&L: $%.2f) [%s]",
            pos.outcome, market_id, exit_price, pnl, reason,
        )
        return pos

    def check_stop_loss_take_profit(
        self, market_id: str, current_price: float
    ) -> Optional[str]:
        """Return "stop_loss" or "take_profit" if threshold hit, else None."""
        pos = self._positions.get(market_id)
        if pos is None:
            return None
        pct = pos.unrealised_pct(current_price)
        if pct <= -pos.stop_loss_pct:
            return "stop_loss"
        if pct >= pos.take_profit_pct:
            return "take_profit"
        return None

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _to_dict(self) -> dict:
        return {
            "starting_balance": self.starting_balance,
            "cash": self.cash,
            "daily_start_equity": self._daily_start_equity,
            "equity_history": self._equity_history[-200:],  # keep last 200
            "positions": {mid: asdict(p) for mid, p in self._positions.items()},
            "closed": [asdict(p) for p in self._closed[-500:]],  # cap closed history
        }

    def save(self) -> None:
        """Atomically save portfolio state with HMAC signature."""
        Path(self._state_path).parent.mkdir(parents=True, exist_ok=True)
        data = self._to_dict()
        sig = sign_state(data)
        payload = {"data": data, "__sig": sig}
        tmp_path = self._state_path + ".tmp"
        with open(tmp_path, "w") as fh:
            json.dump(payload, fh, indent=2, default=str)
        os.replace(tmp_path, self._state_path)

    @classmethod
    def load(cls, state_path: str = _STATE_FILE) -> "Portfolio":
        """Load portfolio from file, verifying HMAC. Returns fresh portfolio on error."""
        if not Path(state_path).exists():
            logger.info("No portfolio state found — starting fresh.")
            return cls()

        try:
            with open(state_path) as fh:
                payload = json.load(fh)

            if "__sig" not in payload:
                logger.error("Portfolio state missing signature — starting fresh.")
                return cls()

            sig = payload["__sig"]
            data = payload["data"]
            if not verify_state(data, sig):
                logger.error("Portfolio HMAC verification FAILED — starting fresh.")
                return cls()

            # Sanity: reject implausible balance
            cfg = get_config()
            cash = float(data.get("cash", 0))
            starting = float(data.get("starting_balance", cfg.starting_balance))
            if cash > starting * _IMPLAUSIBLE_MULTIPLIER:
                logger.error("Portfolio balance %.2f is implausibly large — starting fresh.", cash)
                return cls()

            p = cls()
            p.starting_balance = starting
            p.cash = cash
            p._daily_start_equity = data.get("daily_start_equity", cash)
            p._equity_history = data.get("equity_history", [])
            p._state_path = state_path

            for mid, pos_dict in data.get("positions", {}).items():
                try:
                    p._positions[mid] = Position(**pos_dict)
                except Exception as exc:
                    logger.warning("Skipping bad position %s: %s", mid, exc)

            for pos_dict in data.get("closed", []):
                try:
                    p._closed.append(Position(**pos_dict))
                except Exception as exc:
                    logger.warning("Skipping bad closed position: %s", exc)

            return p

        except Exception as exc:
            logger.error("Failed to load portfolio: %s — starting fresh.", exc)
            return cls()

    # ------------------------------------------------------------------
    # Display
    # ------------------------------------------------------------------

    def print_summary(self) -> None:
        """Print a coloured portfolio summary to stdout."""
        GREEN = "\033[92m"
        RED = "\033[91m"
        CYAN = "\033[96m"
        RESET = "\033[0m"

        pnl_color = GREEN if self.total_pnl >= 0 else RED
        daily_color = GREEN if self.daily_pnl >= 0 else RED

        print(f"\n{CYAN}{'=' * 60}{RESET}")
        print(f"{CYAN}  PORTFOLIO SUMMARY{RESET}")
        print(f"{CYAN}{'=' * 60}{RESET}")
        print(f"  Starting Balance : ${self.starting_balance:>12,.2f}")
        print(f"  Cash Available   : ${self.cash:>12,.2f}")
        print(f"  Total Invested   : ${self.total_invested:>12,.2f}")
        print(f"  Equity           : ${self.equity:>12,.2f}")
        print(f"  Total P&L        : {pnl_color}${self.total_pnl:>+12,.2f}{RESET}")
        print(f"  Daily P&L        : {daily_color}${self.daily_pnl:>+12,.2f}{RESET}")
        print(f"  Open Positions   : {len(self._positions)}")
        print(f"  Closed Trades    : {len(self._closed)}")
        print(f"  Win Rate         : {self.win_rate * 100:.1f}%")
        print(f"  Sharpe Ratio     : {self.sharpe_ratio:.2f}")
        print(f"{CYAN}{'=' * 60}{RESET}\n")
