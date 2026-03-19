"""
News & Sentiment Agent.
Uses web_search tool to find recent news and translate into probability shifts.
"""
from __future__ import annotations

import json
from typing import List, Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.memory import Memory
from core.messaging import MessageBus
from core.polymarket import Market
from core.security import sanitize_for_prompt

_SYSTEM_PROMPT = (
    "You are an investigative journalist and analyst at a trading firm. "
    "You have a nose for what the crowd is missing. "
    "You are skeptical of hype and attuned to signal in noisy information. "
    "You synthesise news into a precise probability assessment. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)

_WEB_SEARCH_TOOL = [
    {
        "type": "web_search_20250305",
        "name": "web_search",
    }
]


class JournalistAgent(BaseAgent):
    """News & sentiment analysis using web search."""

    AGENT_ID = "journalist"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def analyze(self, market: Market) -> AgentOpinion:
        """Search for news and return sentiment-based opinion."""
        safe_question = sanitize_for_prompt(market.question, "question")
        safe_category = sanitize_for_prompt(market.category, "category")

        prompt = (
            f"Research this prediction market:\n"
            f"Question: {safe_question}\n"
            f"Category: {safe_category}\n"
            f"YES price: {market.yes_price:.3f}\n"
            f"NO price: {market.no_price:.3f}\n"
            f"Days to end: {market.days_to_end:.1f}\n\n"
            f"Search for: '{safe_question} news site:reuters.com OR site:bbc.com OR site:apnews.com'\n"
            f"Also search: '{safe_question} latest developments 2025'\n\n"
            "After searching, provide:\n"
            "1. Summaries of 3 most relevant articles\n"
            "2. Media sentiment assessment\n"
            "3. Whether market has priced in recent news\n"
            "4. Narrative risks\n\n"
            "Return JSON with keys: action (BUY_YES|BUY_NO|SKIP), confidence (0-1), "
            "edge (float), reasoning (string ≤400 chars), "
            "sentiment (positive|negative|neutral|conflicted), "
            "narrative_risk (string), sources (list of URLs, max 5), "
            "risk_factors (list of strings), requires_more_info (bool). "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )

        raw = self._call_claude(_SYSTEM_PROMPT, prompt, tools=_WEB_SEARCH_TOOL, max_tokens=4096)
        opinion = self._parse_opinion(raw, market)

        # Store article URLs in memory with 48h TTL
        for url in opinion.sources[:5]:
            self.memory.remember(
                self.AGENT_ID,
                f"source_{market.id}_{hash(url) % 10000}",
                url,
                ttl_hours=48,
            )

        # Store analysis result for accuracy tracking later
        self.memory.remember(
            self.AGENT_ID,
            f"prediction_{market.id}",
            {
                "action": opinion.action,
                "confidence": opinion.confidence,
                "yes_price_at_analysis": market.yes_price,
            },
            ttl_hours=720,  # 30 days
        )

        return opinion

    def record_accuracy(self, market_id: str, resolved_as: str) -> None:
        """Record whether journalist's prediction was correct after resolution."""
        pred = self.memory.recall(self.AGENT_ID, f"prediction_{market_id}")
        if not pred:
            return
        action = pred.get("action", "SKIP")
        if action == "SKIP":
            return
        was_correct = (
            (action == "BUY_YES" and resolved_as == "YES") or
            (action == "BUY_NO" and resolved_as == "NO")
        )
        self.memory.update_agent_accuracy(self.AGENT_ID, was_correct)

    def report(self) -> str:
        return f"JournalistAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
