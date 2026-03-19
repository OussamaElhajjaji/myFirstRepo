"""
Risk Manager Agent.
Compliance officer. Can veto any trade. Protects the portfolio.
"""
from __future__ import annotations

import json
from typing import TYPE_CHECKING, Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.config import get_config
from core.logger import get_logger
from core.memory import Memory
from core.messaging import TOPIC_ALERT_RISK, MessageBus
from core.polymarket import Market
from core.security import sanitize_for_prompt

if TYPE_CHECKING:
    from core.portfolio import Portfolio

logger = get_logger("risk_manager")

_SYSTEM_PROMPT = (
    "You are the chief risk officer of a trading firm. You have seen firms blow up "
    "from overconfidence. Your job is to protect capital first and generate returns "
    "second. You approve trades only when the downside is well understood and bounded. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)


class RiskManagerAgent(BaseAgent):
    """Chief Risk Officer — can veto any trade."""

    AGENT_ID = "risk_manager"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def pre_screen(self, market: Market) -> bool:
        """
        Quick pre-screen before full analysis.
        Returns True (safe to analyse) or False (skip immediately).
        """
        cfg = get_config()

        # Skip markets with very low liquidity
        if market.liquidity < 1000:
            logger.debug("Pre-screen: %s skipped — low liquidity $%.0f", market.id, market.liquidity)
            return False

        # Skip markets ending in < 1 day (too little time)
        if market.days_to_end < 1.0:
            logger.debug("Pre-screen: %s skipped — ends in %.1f days", market.id, market.days_to_end)
            return False

        # Skip markets with extreme prices (near certainty already priced in)
        if market.yes_price > 0.97 or market.no_price > 0.97:
            logger.debug("Pre-screen: %s skipped — extreme price", market.id)
            return False

        return True

    def final_gate(self, trade: "TradeDecision", portfolio: "Portfolio") -> bool:
        """
        Final approval gate. Returns True (approved) or False (rejected).
        Runs all hard risk checks.
        """
        from agents.strategist import TradeDecision
        cfg = get_config()

        # Check circuit breaker
        from core.security import CircuitBreaker
        cb = CircuitBreaker(portfolio.starting_balance, cfg.circuit_breaker_pct)
        if cb.tripped:
            logger.warning("Risk gate: circuit breaker tripped — trade rejected")
            return False

        # Hard limit: max position size
        if trade.size_usd > cfg.max_position_usd:
            logger.warning(
                "Risk gate: trade size $%.2f > max $%.2f",
                trade.size_usd, cfg.max_position_usd,
            )
            return False

        # Hard limit: max open positions
        if len(portfolio.open_positions) >= cfg.max_open_positions:
            logger.warning(
                "Risk gate: max open positions %d reached",
                cfg.max_open_positions,
            )
            return False

        # Category concentration: no single category > 40%
        if trade.action != "SKIP":
            # Find category of the market being traded
            market_category = self.memory.recall(
                self.AGENT_ID, f"market_category_{trade.market_id if hasattr(trade, 'market_id') else ''}"
            )
            if market_category and portfolio.total_invested > 0:
                cat_exposure = sum(
                    p.size_usd
                    for p in portfolio.open_positions
                    if p.category == market_category
                )
                concentration = (cat_exposure + trade.size_usd) / portfolio.equity
                if concentration > 0.40:
                    logger.warning(
                        "Risk gate: category concentration %.1f%% > 40%%", concentration * 100
                    )
                    return False

        # Max loss scenario: if ALL open trades resolve against us, equity > 50%?
        worst_case_loss = portfolio.total_invested + trade.size_usd
        if portfolio.equity - worst_case_loss < portfolio.starting_balance * 0.50:
            logger.warning(
                "Risk gate: worst-case equity $%.2f < 50%% of starting $%.2f",
                portfolio.equity - worst_case_loss,
                portfolio.starting_balance * 0.50,
            )
            return False

        # AI sanity check
        approved = self._ai_gate(trade, portfolio)
        return approved

    def _ai_gate(self, trade: "TradeDecision", portfolio: "Portfolio") -> bool:
        """Ask Claude for final approval on borderline cases."""
        prompt = (
            f"Review this trade for risk approval:\n"
            f"Action: {trade.action}\n"
            f"Outcome: {trade.outcome}\n"
            f"Size: ${trade.size_usd:.2f}\n"
            f"Confidence: {trade.confidence:.2%}\n"
            f"Consensus score: {trade.consensus_score:.3f}\n"
            f"Portfolio equity: ${portfolio.equity:.2f}\n"
            f"Open positions: {len(portfolio.open_positions)}\n"
            f"Total invested: ${portfolio.total_invested:.2f}\n"
            f"Investment memo: {sanitize_for_prompt(trade.investment_memo[:200], 'memo')}\n\n"
            "Should this trade be approved? Consider: drawdown risk, position concentration, "
            "portfolio health, and whether the edge justifies the risk.\n"
            "Return JSON: {\"approved\": true|false, \"reason\": \"string\"}. "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )
        raw = self._call_claude(_SYSTEM_PROMPT, prompt, max_tokens=256)
        try:
            data = json.loads(raw)
            approved = bool(data.get("approved", False))
            reason = data.get("reason", "")
            if not approved:
                logger.info("AI risk gate rejected: %s", reason)
            return approved
        except (json.JSONDecodeError, TypeError):
            logger.warning("AI risk gate parse failed — defaulting to reject")
            return False

    def daily_risk_report(self, portfolio: "Portfolio") -> dict:
        """Generate and publish daily risk report."""
        cfg = get_config()
        report = {
            "total_exposure": portfolio.total_invested,
            "equity": portfolio.equity,
            "daily_pnl": portfolio.daily_pnl,
            "open_positions": len(portfolio.open_positions),
            "largest_position": max(
                (p.size_usd for p in portfolio.open_positions), default=0.0
            ),
            "win_rate": portfolio.win_rate,
            "warnings": [],
        }

        # Category concentration check
        categories: dict = {}
        for pos in portfolio.open_positions:
            categories[pos.category] = categories.get(pos.category, 0) + pos.size_usd
        for cat, exposure in categories.items():
            pct = exposure / portfolio.equity if portfolio.equity > 0 else 0.0
            if pct > 0.80:
                report["warnings"].append(f"Category {cat} at {pct:.0%} of equity (>80% of 40% limit)")

        # Approaching max positions
        pos_pct = len(portfolio.open_positions) / cfg.max_open_positions
        if pos_pct > 0.80:
            report["warnings"].append(
                f"Open positions: {len(portfolio.open_positions)}/{cfg.max_open_positions} (>80%)"
            )

        self.bus.publish(TOPIC_ALERT_RISK, report)
        logger.info("Daily risk report published: %s", report)
        return report

    def analyze(self, market: Market) -> AgentOpinion:
        """Standard analyze interface (pre-screen + opinion)."""
        if not self.pre_screen(market):
            return self._safe_skip(market, "Failed pre-screen")
        return AgentOpinion(
            agent_id=self.agent_id,
            action="SKIP",
            confidence=0.0,
            edge=0.0,
            reasoning="Risk manager pre-screen passed. Awaiting full trade decision.",
        )

    def report(self) -> str:
        return f"RiskManagerAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
