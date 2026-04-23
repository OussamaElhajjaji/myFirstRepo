"""
Main async trading loop.
Runs every LOOP_INTERVAL_SEC seconds and orchestrates all agents.
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional

from core.config import get_config
from core.logger import get_logger, setup_logging
from core.memory import Memory
from core.messaging import get_bus, TOPIC_CYCLE_COMPLETE
from core.polymarket import Market, PolymarketClient
from core.portfolio import Portfolio
from core.security import CircuitBreaker

from agents.analyst import AnalystAgent
from agents.base_agent import AgentOpinion
from agents.contrarian import ContrarianAgent
from agents.execution import ExecutionAgent
from agents.historian import HistorianAgent
from agents.journalist import JournalistAgent
from agents.macro import MacroAgent
from agents.risk_manager import RiskManagerAgent
from agents.security_agent import SecurityAgent
from agents.strategist import StrategistAgent, TradeDecision

logger = get_logger("main_loop")


class TradingFirm:
    """Orchestrates all agents in the trading loop."""

    def __init__(self) -> None:
        self.cfg = get_config()
        self.memory = Memory(f"{self.cfg.log_dir}/memory.db")
        self.bus = get_bus()
        self.portfolio = Portfolio.load(f"{self.cfg.log_dir}/portfolio_state.json")
        self.polymarket = PolymarketClient()
        self.circuit_breaker = CircuitBreaker(
            self.portfolio.starting_balance,
            self.cfg.circuit_breaker_pct,
        )

        # Instantiate all agents
        self.security_agent = SecurityAgent(self.memory, self.bus)
        self.analyst = AnalystAgent(self.memory, self.bus)
        self.journalist = JournalistAgent(self.memory, self.bus)
        self.macro = MacroAgent(self.memory, self.bus)
        self.historian = HistorianAgent(self.memory, self.bus)
        self.risk_manager = RiskManagerAgent(self.memory, self.bus)
        self.contrarian = ContrarianAgent(self.memory, self.bus)
        self.strategist = StrategistAgent(self.memory, self.bus)
        self.execution = ExecutionAgent(self.memory, self.polymarket, self.bus)

        self._cycle_count = 0
        self._last_daily_report = datetime.now(timezone.utc)
        self._paused = False

        logger.info(
            "TradingFirm initialised | paper=%s | profile=%s | equity=$%.2f",
            self.cfg.paper_trading,
            self.cfg.risk_profile.name,
            self.portfolio.equity,
        )

    # ------------------------------------------------------------------
    # Main loop
    # ------------------------------------------------------------------

    async def run(self) -> None:
        """Main async loop."""
        logger.info("Starting trading loop (interval=%ds)", self.cfg.loop_interval_sec)
        while True:
            if not self._paused:
                try:
                    await self._run_cycle()
                except RuntimeError as exc:
                    # Circuit breaker or other halt condition
                    logger.critical("HALT: %s", exc)
                    self.bus.publish("circuit.breaker", {"error": str(exc)})
                    await asyncio.sleep(self.cfg.loop_interval_sec * 5)
                except Exception as exc:
                    logger.error("Unhandled cycle error: %s", exc, exc_info=True)
                    await asyncio.sleep(30)

            await asyncio.sleep(self.cfg.loop_interval_sec)

    async def _run_cycle(self) -> None:
        """Execute one full trading cycle."""
        self._cycle_count += 1
        cycle_start = time.monotonic()
        logger.info("=" * 60)
        logger.info("CYCLE %d START", self._cycle_count)

        trades_opened = 0
        positions_closed = 0
        markets_analysed = 0

        # STEP 1 — Security & health check
        if not await self._step_health_check():
            logger.warning("Health check failed — skipping cycle")
            return

        # STEP 2 — Fetch & pre-screen markets
        qualifying_markets = await self._step_fetch_markets()
        logger.info("Qualifying markets: %d", len(qualifying_markets))

        # STEPS 3-8 — Analyse each market
        for market in qualifying_markets[:self.cfg.max_markets_per_run]:
            result = await self._analyse_market(market)
            markets_analysed += 1
            if result:
                trades_opened += 1

        # STEP 9 — Position monitoring
        positions_closed += await self._step_monitor_positions()

        # STEP 10 — Update agent accuracy
        await self._step_update_accuracy()

        # Daily risk report
        now = datetime.now(timezone.utc)
        if (now - self._last_daily_report).total_seconds() > 86400:
            self.risk_manager.daily_risk_report(self.portfolio)
            self._last_daily_report = now

        # Clean up expired memory
        self.memory.forget_expired()

        elapsed = time.monotonic() - cycle_start
        logger.info(
            "CYCLE %d DONE | markets=%d | opened=%d | closed=%d | equity=$%.2f | time=%.1fs",
            self._cycle_count, markets_analysed, trades_opened, positions_closed,
            self.portfolio.equity, elapsed,
        )

        # STEP 11 — Publish cycle summary
        self.bus.publish(TOPIC_CYCLE_COMPLETE, {
            "cycle_number": self._cycle_count,
            "markets_analysed": markets_analysed,
            "trades_opened": trades_opened,
            "positions_closed": positions_closed,
            "portfolio_equity": self.portfolio.equity,
            "elapsed_sec": round(elapsed, 1),
        })

    # ------------------------------------------------------------------
    # Steps
    # ------------------------------------------------------------------

    async def _step_health_check(self) -> bool:
        """STEP 1: Verify environment is healthy."""
        loop = asyncio.get_event_loop()
        healthy = await loop.run_in_executor(None, self.security_agent.scan_environment)
        if not healthy:
            return False

        # Check circuit breaker
        try:
            self.circuit_breaker.check(self.portfolio.equity)
        except RuntimeError as exc:
            raise  # propagate to main loop

        return True

    async def _step_fetch_markets(self) -> List[Market]:
        """STEP 2: Fetch markets and pre-screen with security + risk."""
        loop = asyncio.get_event_loop()
        limit = self.cfg.max_markets_per_run * 3

        markets = await loop.run_in_executor(
            None, self.polymarket.get_markets, limit
        )

        qualifying: List[Market] = []
        for market in markets:
            # Security scan
            assessment = await loop.run_in_executor(
                None, self.security_agent.scan_market, market
            )
            if assessment.severity in ("high", "critical"):
                logger.debug("Market %s blocked by security: %s", market.id, assessment.flags)
                continue

            # Risk pre-screen
            ok = await loop.run_in_executor(
                None, self.risk_manager.pre_screen, market
            )
            if not ok:
                continue

            qualifying.append(market)

        return qualifying

    async def _analyse_market(self, market: Market) -> bool:
        """STEPS 3-8: Full analysis pipeline for one market. Returns True if trade placed."""
        loop = asyncio.get_event_loop()

        # STEP 3 — Parallel agent analysis
        tasks = [
            loop.run_in_executor(None, self.analyst.analyze, market),
            loop.run_in_executor(None, self.journalist.analyze, market),
            loop.run_in_executor(None, self.macro.analyze, market),
            loop.run_in_executor(None, self.historian.analyze, market),
        ]
        opinions: List[AgentOpinion] = list(await asyncio.gather(*tasks))

        # STEP 4 — Consensus (Strategist)
        trade = await loop.run_in_executor(
            None, self.strategist.analyze_all, market, opinions
        )
        if trade.action == "SKIP":
            logger.info("Market %s → SKIP (consensus): %s", market.id, trade.investment_memo)
            return False

        # STEP 5 — Contrarian stress test
        contrarian_report = await loop.run_in_executor(
            None, self.contrarian.stress_test, market, trade
        )
        if contrarian_report.veto:
            logger.info(
                "Market %s → SKIP (contrarian veto, conf=%.2f): %s",
                market.id, contrarian_report.veto_confidence, contrarian_report.blind_spots,
            )
            return False

        # STEP 6 — Risk gate
        approved = await loop.run_in_executor(
            None, self.risk_manager.final_gate, trade, self.portfolio
        )
        if not approved:
            logger.info("Market %s → SKIP (risk gate)", market.id)
            return False

        # STEP 7 — Final circuit breaker check (raises on trip)
        self.circuit_breaker.check(self.portfolio.equity)

        # STEP 8 — Execute
        report = await loop.run_in_executor(
            None, self.execution.execute, trade, market, self.portfolio
        )
        if not report.success:
            logger.warning("Execution failed for %s: %s", market.id, report.error)
            return False

        return True

    async def _step_monitor_positions(self) -> int:
        """STEP 9: Monitor open positions for stop-loss/take-profit."""
        loop = asyncio.get_event_loop()
        closed_count = 0

        for pos in list(self.portfolio.open_positions):
            market = await loop.run_in_executor(
                None, self.polymarket.get_market_by_id, pos.market_id
            )
            if market is None:
                continue

            current_price = market.yes_price if pos.outcome == "YES" else market.no_price
            trigger = self.portfolio.check_stop_loss_take_profit(pos.market_id, current_price)

            if trigger:
                closed = self.portfolio.close_position(pos.market_id, current_price, trigger)
                if closed:
                    from core.messaging import TOPIC_POSITION_CLOSED
                    self.bus.publish(TOPIC_POSITION_CLOSED, {
                        "market_id": pos.market_id,
                        "outcome": pos.outcome,
                        "exit_price": current_price,
                        "pnl": closed.pnl,
                        "reason": trigger,
                    })
                    closed_count += 1

        return closed_count

    async def _step_update_accuracy(self) -> None:
        """STEP 10: Update agent accuracy for recently resolved markets."""
        # Check each open position's market for resolution
        loop = asyncio.get_event_loop()
        for pos in list(self.portfolio.open_positions):
            market = await loop.run_in_executor(
                None, self.polymarket.get_market_by_id, pos.market_id
            )
            if market is None:
                continue
            # Market is considered resolved if yes_price > 0.99 or no_price > 0.99
            if market.yes_price > 0.99:
                resolved_as = "YES"
            elif market.no_price > 0.99:
                resolved_as = "NO"
            else:
                continue  # still active

            # Update historian
            pred = self.memory.recall(HistorianAgent.AGENT_ID, f"prediction_{market.id}")
            if pred:
                predicted = pred.get("action", "SKIP")
                was_correct = (
                    (predicted == "BUY_YES" and resolved_as == "YES") or
                    (predicted == "BUY_NO" and resolved_as == "NO")
                )
                if predicted != "SKIP":
                    self.memory.update_agent_accuracy(HistorianAgent.AGENT_ID, was_correct)

            # Record outcome in memory for future base rates
            self.memory.record_market_outcome(
                market.id, market.question, resolved_as
            )

    def pause(self) -> None:
        self._paused = True
        logger.info("Trading loop paused.")

    def resume(self) -> None:
        self._paused = False
        logger.info("Trading loop resumed.")

    @property
    def is_paused(self) -> bool:
        return self._paused


# Singleton for API access
_firm: Optional[TradingFirm] = None


def get_firm() -> TradingFirm:
    global _firm
    if _firm is None:
        _firm = TradingFirm()
    return _firm


async def main() -> None:
    setup_logging(get_config().log_dir)
    firm = get_firm()
    firm.portfolio.print_summary()
    await firm.run()


if __name__ == "__main__":
    asyncio.run(main())
