"""
Quantitative Data Analyst Agent.
Pure numbers, no narrative. Statistical mispricings and Kelly sizing.
"""
from __future__ import annotations

import json
import math
from typing import Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.memory import Memory
from core.messaging import MessageBus
from core.polymarket import Market
from core.security import sanitize_for_prompt

_SYSTEM_PROMPT = (
    "You are a quantitative analyst at a hedge fund. You trust only numbers and statistics. "
    "You are deeply skeptical of narrative and recency bias. You calculate edge precisely. "
    "You only recommend trading when you have a statistically significant edge. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)


class AnalystAgent(BaseAgent):
    """Quantitative analyst — statistics and edge calculation."""

    AGENT_ID = "analyst"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def analyze(self, market: Market) -> AgentOpinion:
        """Quantitative analysis of a market."""
        # --- Volume trend analysis ---
        vol_7d_key = f"vol_7d_{market.id}"
        vol_30d_key = f"vol_30d_{market.id}"
        vol_7d_avg = self.memory.recall(self.AGENT_ID, vol_7d_key) or market.volume
        vol_30d_avg = self.memory.recall(self.AGENT_ID, vol_30d_key) or market.volume

        volume_spike = market.volume / vol_7d_avg if vol_7d_avg > 0 else 1.0
        informed_trading_signal = volume_spike > 3.0

        # Store current volume for future trend calculation
        self.memory.remember(self.AGENT_ID, vol_7d_key, market.volume, ttl_hours=168)
        self.memory.remember(self.AGENT_ID, vol_30d_key, market.volume, ttl_hours=720)

        # --- Price drift ---
        price_key = f"price_24h_{market.id}"
        price_24h_ago = self.memory.recall(self.AGENT_ID, price_key)
        self.memory.remember(self.AGENT_ID, price_key, market.yes_price, ttl_hours=25)
        price_drift = (
            market.yes_price - price_24h_ago if price_24h_ago is not None else 0.0
        )

        # --- Price sum deviation (potential arb) ---
        price_sum = market.yes_price + market.no_price
        price_sum_deviation = abs(price_sum - 1.0)
        arb_opportunity = price_sum_deviation > 0.05

        # --- Kelly Criterion (rough) ---
        # Estimate true probability from our analysis context
        # Kelly = (bp - q) / b where b = odds (1/p - 1), p = win prob
        # Use edge as proxy
        edge_estimate = price_sum_deviation / 2.0 if arb_opportunity else 0.0

        # Build prompt
        prompt = (
            f"Analyse this prediction market quantitatively:\n"
            f"Question: {sanitize_for_prompt(market.question, 'question')}\n"
            f"YES price: {market.yes_price:.4f}\n"
            f"NO price: {market.no_price:.4f}\n"
            f"Price sum: {price_sum:.4f} (deviation from 1.0: {price_sum_deviation:.4f})\n"
            f"Volume: ${market.volume:,.0f}\n"
            f"Liquidity: ${market.liquidity:,.0f}\n"
            f"7d avg volume: ${vol_7d_avg:,.0f}\n"
            f"Volume spike ratio: {volume_spike:.2f}x\n"
            f"Informed trading signal: {informed_trading_signal}\n"
            f"24h price drift: {price_drift:+.4f}\n"
            f"Arb opportunity: {arb_opportunity}\n"
            f"Days to end: {market.days_to_end:.1f}\n\n"
            "Calculate statistical edge and provide trading recommendation.\n"
            "Return JSON with keys: action (BUY_YES|BUY_NO|SKIP), confidence (0-1), "
            "edge (float, expected edge vs market price), kelly_fraction (0-1), "
            "reasoning (string ≤300 chars), risk_factors (list of strings). "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )

        raw = self._call_claude(_SYSTEM_PROMPT, prompt)
        return self._parse_opinion(raw, market)

    def report(self) -> str:
        return f"AnalystAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
