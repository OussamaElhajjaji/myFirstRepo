"""
Execution Agent — purely deterministic, no AI inference.
Places orders, records fills, publishes trade events.
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.config import get_config
from core.logger import get_logger
from core.memory import Memory
from core.messaging import MessageBus, TOPIC_TRADE_EXECUTED
from core.polymarket import Market, PolymarketClient
from core.security import validate_usd_amount

if TYPE_CHECKING:
    from agents.strategist import TradeDecision
    from core.portfolio import Portfolio

logger = get_logger("execution")


@dataclass
class ExecutionReport:
    """Result of an execution attempt."""

    success: bool
    market_id: str
    outcome: str
    expected_price: float
    actual_price: float
    size_requested: float
    size_filled: float
    slippage_pct: float
    order_id: str
    paper: bool = True
    error: str = ""


class ExecutionAgent(BaseAgent):
    """Deterministic execution — places orders and records fills."""

    AGENT_ID = "execution"

    def __init__(
        self,
        memory: Memory,
        polymarket: PolymarketClient,
        bus: Optional[MessageBus] = None,
    ) -> None:
        super().__init__(self.AGENT_ID, memory, bus)
        self._polymarket = polymarket

    def execute(
        self,
        trade: "TradeDecision",
        market: Market,
        portfolio: "Portfolio",
    ) -> ExecutionReport:
        """
        Execute a trade decision:
        1. Check orderbook depth for slippage
        2. Adjust size if orderbook thin
        3. Validate final size against MAX_POSITION_USD
        4. Place order
        5. Retry once on failure
        6. Record fill
        7. Publish trade.executed event
        """
        cfg = get_config()
        outcome = trade.outcome
        expected_price = market.yes_price if outcome == "YES" else market.no_price

        # --- 1. Estimate slippage from orderbook depth ---
        size_adjusted = self._adjust_for_slippage(market, trade.size_usd, outcome)

        # --- 2. Final size validation ---
        size_adjusted = validate_usd_amount(size_adjusted)
        if size_adjusted > cfg.max_position_usd:
            size_adjusted = cfg.max_position_usd
        if size_adjusted < 1.0:
            return ExecutionReport(
                success=False,
                market_id=market.id,
                outcome=outcome,
                expected_price=expected_price,
                actual_price=0.0,
                size_requested=trade.size_usd,
                size_filled=0.0,
                slippage_pct=0.0,
                order_id="",
                error="Adjusted size too small ($<1.00)",
            )

        # --- 3. Place order with one retry ---
        result = self._polymarket.buy(market, outcome, size_adjusted)
        if not result.success:
            logger.warning("First buy attempt failed: %s — retrying in 2s", result.error)
            time.sleep(2)
            result = self._polymarket.buy(market, outcome, size_adjusted)

        if not result.success:
            return ExecutionReport(
                success=False,
                market_id=market.id,
                outcome=outcome,
                expected_price=expected_price,
                actual_price=0.0,
                size_requested=trade.size_usd,
                size_filled=0.0,
                slippage_pct=0.0,
                order_id="",
                error=result.error,
            )

        # --- 4. Record fill ---
        slippage_pct = (
            abs(result.price - expected_price) / expected_price
            if expected_price > 0
            else 0.0
        )

        try:
            portfolio.open_position(
                market_id=market.id,
                question=market.question,
                outcome=outcome,
                entry_price=result.price,
                size_usd=size_adjusted,
                category=market.category,
                order_id=result.order_id,
                agent_memo=trade.investment_memo[:200],
            )
        except RuntimeError as exc:
            logger.error("Portfolio open_position failed: %s", exc)
            return ExecutionReport(
                success=False,
                market_id=market.id,
                outcome=outcome,
                expected_price=expected_price,
                actual_price=result.price,
                size_requested=trade.size_usd,
                size_filled=0.0,
                slippage_pct=slippage_pct,
                order_id=result.order_id,
                error=str(exc),
            )

        report = ExecutionReport(
            success=True,
            market_id=market.id,
            outcome=outcome,
            expected_price=expected_price,
            actual_price=result.price,
            size_requested=trade.size_usd,
            size_filled=size_adjusted,
            slippage_pct=slippage_pct,
            order_id=result.order_id,
            paper=result.paper,
        )

        # --- 5. Publish event ---
        self.bus.publish(TOPIC_TRADE_EXECUTED, {
            "market_id": market.id,
            "question": market.question[:100],
            "outcome": outcome,
            "size_usd": size_adjusted,
            "price": result.price,
            "slippage_pct": slippage_pct,
            "order_id": result.order_id,
            "paper": result.paper,
        })

        logger.info(
            "Trade executed: %s %s $%.2f @ %.3f (slippage: %.2f%%)",
            outcome, market.id, size_adjusted, result.price, slippage_pct * 100,
        )

        return report

    def _adjust_for_slippage(
        self, market: Market, size_usd: float, outcome: str
    ) -> float:
        """
        Reduce size by up to 50% if orderbook is thin relative to trade size.
        Simple heuristic: if trade > 10% of liquidity, reduce proportionally.
        """
        if market.liquidity <= 0:
            return size_usd * 0.5

        ratio = size_usd / market.liquidity
        if ratio > 0.10:
            # Thin market: reduce size
            adjusted = size_usd * (1 - min(0.5, ratio - 0.10))
            logger.info(
                "Slippage adjustment: $%.2f → $%.2f (liquidity $%.0f)",
                size_usd, adjusted, market.liquidity,
            )
            return adjusted
        return size_usd

    def analyze(self, market: Market) -> AgentOpinion:
        """Execution agent has no opinion — always returns SKIP."""
        return self._safe_skip(market, "Execution agent has no opinion")

    def report(self) -> str:
        return f"ExecutionAgent | deterministic | paused={self._paused}"
