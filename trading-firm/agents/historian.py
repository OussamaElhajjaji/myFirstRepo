"""
Historical Pattern Agent.
Base rates and historical precedents from memory database.
"""
from __future__ import annotations

import json
from typing import Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.memory import Memory
from core.messaging import MessageBus
from core.polymarket import Market
from core.security import sanitize_for_prompt

_SYSTEM_PROMPT = (
    "You are an economic historian and statistician. You have studied thousands "
    "of prediction markets. You trust base rates above all else. You are deeply "
    "humble about your ability to predict individual outcomes but confident in "
    "aggregate statistics. You always ask: what has happened in similar cases in "
    "the past? Respond ONLY with valid JSON. No markdown. No explanation."
)


class HistorianAgent(BaseAgent):
    """Base rate and historical pattern analysis."""

    AGENT_ID = "historian"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def analyze(self, market: Market) -> AgentOpinion:
        """Analyse historical base rates and patterns for a market."""
        safe_question = sanitize_for_prompt(market.question, "question")
        safe_category = sanitize_for_prompt(market.category, "category")

        # Query memory for similar past markets
        similar_by_category = self.memory.search_market_outcomes(
            market.category, limit=10
        )
        similar_by_keywords = self._extract_keywords_and_search(market.question)

        # Calculate empirical base rate
        cat_total = len(similar_by_category)
        cat_yes = sum(1 for m in similar_by_category if m.get("resolved_as") == "YES")
        base_rate = cat_yes / cat_total if cat_total > 0 else 0.5

        similar_summary = (
            f"Category matches: {cat_total} markets, {cat_yes} resolved YES "
            f"(base rate: {base_rate:.2%}).\n"
            f"Keyword matches: {len(similar_by_keywords)} markets.\n"
        )

        if similar_by_keywords:
            kw_yes = sum(1 for m in similar_by_keywords if m.get("resolved_as") == "YES")
            similar_summary += f"Keyword base rate: {kw_yes}/{len(similar_by_keywords)} YES."

        prompt = (
            f"Provide historical analysis for this prediction market:\n"
            f"Question: {safe_question}\n"
            f"Category: {safe_category}\n"
            f"YES price: {market.yes_price:.3f}\n"
            f"Days to end: {market.days_to_end:.1f}\n\n"
            f"Historical data from our database:\n{similar_summary}\n\n"
            "Assess:\n"
            "1. Does the current price align with historical base rates?\n"
            "2. Are there seasonal patterns or precedents?\n"
            "3. Is this market unprecedented (no historical analogues)?\n"
            "4. How does historical evidence affect the probability?\n\n"
            "Return JSON with keys: action (BUY_YES|BUY_NO|SKIP), confidence (0-1), "
            "edge (float), base_rate (float), historical_precedents (int count), "
            "reasoning (string ≤300 chars), risk_factors (list of strings). "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )

        raw = self._call_claude(_SYSTEM_PROMPT, prompt)
        opinion = self._parse_opinion(raw, market)

        # Store prediction for later accuracy tracking
        self.memory.remember(
            self.AGENT_ID,
            f"prediction_{market.id}",
            {
                "action": opinion.action,
                "confidence": opinion.confidence,
                "category": market.category,
                "yes_price_at_analysis": market.yes_price,
            },
            ttl_hours=720,
        )

        return opinion

    def _extract_keywords_and_search(self, question: str) -> list:
        """Extract keywords from question and search for similar resolved markets."""
        # Simple keyword extraction: words longer than 4 chars
        words = [w.strip(".,?!\"'") for w in question.split() if len(w) > 4]
        results = []
        for word in words[:3]:  # limit to 3 keywords
            matches = self.memory.search_market_outcomes(word, limit=5)
            results.extend(matches)
        return results

    def record_market_resolution(
        self,
        market_id: str,
        question: str,
        category: str,
        resolved_as: str,
        predicted_action: str,
    ) -> None:
        """Record a market resolution and update accuracy."""
        self.memory.record_market_outcome(market_id, question, resolved_as)

        # Track accuracy
        if predicted_action != "SKIP":
            was_correct = (
                (predicted_action == "BUY_YES" and resolved_as == "YES") or
                (predicted_action == "BUY_NO" and resolved_as == "NO")
            )
            self.memory.update_agent_accuracy(self.AGENT_ID, was_correct)

    def report(self) -> str:
        return f"HistorianAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
