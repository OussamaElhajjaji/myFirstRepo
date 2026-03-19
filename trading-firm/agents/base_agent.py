"""
Abstract base class for all trading agents.
Provides Anthropic client, memory, message bus, accuracy tracking,
and safe Claude API call wrapper.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import anthropic

from core.config import get_config
from core.logger import get_logger
from core.memory import Memory
from core.messaging import MessageBus, get_bus
from core.polymarket import Market
from core.security import (
    get_rate_limiter,
    sanitize_for_prompt,
    validate_action,
    validate_usd_amount,
)

logger = get_logger("base_agent")

_rl = get_rate_limiter()
# Anthropic API rate limit: 50 calls/min per agent (conservative)
_CLAUDE_LIMIT = 50
_CLAUDE_WINDOW = 60.0


@dataclass
class AgentOpinion:
    """Structured opinion output from an agent analysis."""

    agent_id: str
    action: str                      # "BUY_YES" | "BUY_NO" | "SKIP"
    confidence: float                # 0.0–1.0
    edge: float                      # estimated edge over market price
    reasoning: str
    risk_factors: List[str] = field(default_factory=list)
    requires_more_info: bool = False
    sources: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.action = validate_action(self.action)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))
        self.edge = max(-1.0, min(1.0, float(self.edge)))


class BaseAgent(ABC):
    """Abstract base for all trading firm agents."""

    def __init__(
        self,
        agent_id: str,
        memory: Memory,
        bus: Optional[MessageBus] = None,
    ) -> None:
        self.agent_id = agent_id
        self.memory = memory
        self.bus = bus or get_bus()
        cfg = get_config()
        self.client = anthropic.Anthropic(api_key=cfg.anthropic_api_key)
        self.accuracy: float = memory.get_agent_accuracy(agent_id)
        self._paused: bool = False
        logger.info("Agent %s initialised (accuracy=%.2f)", agent_id, self.accuracy)

    # ------------------------------------------------------------------
    # Abstract interface
    # ------------------------------------------------------------------

    @abstractmethod
    def analyze(self, market: Market) -> AgentOpinion:
        """Analyse a market and return an opinion."""
        ...

    @abstractmethod
    def report(self) -> str:
        """Return a human-readable status report for this agent."""
        ...

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _call_claude(
        self,
        system: str,
        prompt: str,
        tools: Optional[List[dict]] = None,
        max_tokens: int = 2048,
    ) -> str:
        """
        Call Claude API with rate limiting and error handling.
        Records last_analysis_at in memory. Returns raw text content.
        """
        if self._paused:
            return json.dumps({"action": "SKIP", "reasoning": "Agent is paused."})

        _rl.wait_if_needed(f"claude_{self.agent_id}", _CLAUDE_LIMIT, _CLAUDE_WINDOW)

        self.memory.remember(
            self.agent_id,
            "last_analysis_at",
            datetime.now(timezone.utc).isoformat(),
        )

        kwargs: Dict[str, Any] = {
            "model": "claude-sonnet-4-6",
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": prompt}],
        }
        if tools:
            kwargs["tools"] = tools

        try:
            response = self.client.messages.create(**kwargs)
            # Extract text from first content block
            for block in response.content:
                if hasattr(block, "text"):
                    return block.text
            return "{}"
        except anthropic.APIError as exc:
            logger.error("Claude API error for %s: %s", self.agent_id, exc)
            return json.dumps({"action": "SKIP", "reasoning": f"API error: {exc}"})
        except Exception as exc:
            logger.error("Unexpected error calling Claude for %s: %s", self.agent_id, exc)
            return json.dumps({"action": "SKIP", "reasoning": f"Unexpected error: {exc}"})

    def _safe_skip(self, market: Market, reason: str) -> AgentOpinion:
        """Return a safe SKIP opinion with a reason logged."""
        logger.info("%s SKIP %s: %s", self.agent_id, market.id, reason)
        return AgentOpinion(
            agent_id=self.agent_id,
            action="SKIP",
            confidence=0.0,
            edge=0.0,
            reasoning=reason,
        )

    def _parse_opinion(self, raw: str, market: Market) -> AgentOpinion:
        """
        Parse JSON from Claude response into AgentOpinion.
        Falls back to SKIP on any parse error.
        """
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown code block
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
            if match:
                try:
                    data = json.loads(match.group(1))
                except json.JSONDecodeError:
                    return self._safe_skip(market, f"JSON parse failed: {raw[:100]}")
            else:
                return self._safe_skip(market, f"JSON parse failed: {raw[:100]}")

        return AgentOpinion(
            agent_id=self.agent_id,
            action=validate_action(data.get("action", "SKIP")),
            confidence=float(data.get("confidence", 0.0)),
            edge=float(data.get("edge", 0.0)),
            reasoning=str(data.get("reasoning", "")),
            risk_factors=list(data.get("risk_factors", [])),
            requires_more_info=bool(data.get("requires_more_info", False)),
            sources=list(data.get("sources", [])),
        )

    def pause(self) -> None:
        """Pause this agent (it will return SKIP for all analyses)."""
        self._paused = True
        logger.info("Agent %s paused.", self.agent_id)

    def resume(self) -> None:
        """Resume this agent."""
        self._paused = False
        logger.info("Agent %s resumed.", self.agent_id)

    @property
    def is_paused(self) -> bool:
        return self._paused

    def get_status(self) -> dict:
        """Return current agent status for dashboard."""
        last_at = self.memory.recall(self.agent_id, "last_analysis_at")
        return {
            "agent_id": self.agent_id,
            "paused": self._paused,
            "accuracy": self.accuracy,
            "last_analysis_at": last_at,
        }
