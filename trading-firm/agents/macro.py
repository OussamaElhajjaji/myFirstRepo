"""
Macro & Political Context Agent.
Big picture awareness — elections, central banks, geopolitics.
"""
from __future__ import annotations

from typing import Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.memory import Memory
from core.messaging import MessageBus
from core.polymarket import Market
from core.security import sanitize_for_prompt

_SYSTEM_PROMPT = (
    "You are a macroeconomist and political analyst with 20 years of experience. "
    "You understand second and third-order effects. You always consider the political "
    "and economic context before any prediction market analysis. You are never surprised "
    "by macro events that were clearly foreseeable. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)

_WEB_SEARCH_TOOL = [{"type": "web_search_20250305", "name": "web_search"}]


class MacroAgent(BaseAgent):
    """Macro and political context analysis."""

    AGENT_ID = "macro"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def analyze(self, market: Market) -> AgentOpinion:
        """Assess macro and political context for a market."""
        safe_question = sanitize_for_prompt(market.question, "question")
        safe_category = sanitize_for_prompt(market.category, "category")

        # Check for stored macro calendar
        macro_calendar = self.memory.recall(self.AGENT_ID, "macro_calendar")
        calendar_note = (
            f"Current macro event calendar: {macro_calendar}"
            if macro_calendar
            else "No macro calendar stored."
        )

        prompt = (
            f"Analyse the macro and political context for this prediction market:\n"
            f"Question: {safe_question}\n"
            f"Category: {safe_category}\n"
            f"YES price: {market.yes_price:.3f}\n"
            f"Days to end: {market.days_to_end:.1f}\n"
            f"{calendar_note}\n\n"
            "Search for relevant macro events, central bank decisions, elections, "
            "or geopolitical developments affecting this market.\n\n"
            "Assess:\n"
            "1. How does the macro environment affect the probability?\n"
            "2. Are there upcoming events that could shift the outcome?\n"
            "3. Is this market correlated with other upcoming events?\n"
            "4. Score macro tailwind: +1 (strongly YES), -1 (strongly NO)\n\n"
            "Return JSON with keys: action (BUY_YES|BUY_NO|SKIP), confidence (0-1), "
            "edge (float), macro_tailwind (float -1 to +1), "
            "reasoning (string ≤300 chars), upcoming_events (list of strings), "
            "risk_factors (list of strings), sources (list of URLs, max 5). "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )

        raw = self._call_claude(_SYSTEM_PROMPT, prompt, tools=_WEB_SEARCH_TOOL, max_tokens=3072)
        opinion = self._parse_opinion(raw, market)

        # Update macro calendar weekly
        calendar_age = self.memory.recall(self.AGENT_ID, "macro_calendar_updated_at")
        if not calendar_age:
            self._update_macro_calendar()

        return opinion

    def _update_macro_calendar(self) -> None:
        """Search for upcoming macro events and store in memory."""
        from datetime import datetime, timezone
        prompt = (
            "Search for upcoming major macro events in the next 30 days: "
            "Fed meetings, ECB meetings, major elections, economic data releases. "
            "Return a JSON list of event strings. "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )
        raw = self._call_claude(_SYSTEM_PROMPT, prompt, tools=_WEB_SEARCH_TOOL, max_tokens=1024)
        import json
        try:
            events = json.loads(raw)
            self.memory.remember(self.AGENT_ID, "macro_calendar", events, ttl_hours=168)
            self.memory.remember(
                self.AGENT_ID,
                "macro_calendar_updated_at",
                datetime.now(timezone.utc).isoformat(),
                ttl_hours=168,
            )
        except json.JSONDecodeError:
            pass

    def report(self) -> str:
        return f"MacroAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
