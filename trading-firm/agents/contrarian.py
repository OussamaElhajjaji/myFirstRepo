"""
Contrarian / Devil's Advocate Agent.
Always argues the other side. Prevents groupthink. Has veto power.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.memory import Memory
from core.messaging import MessageBus
from core.polymarket import Market
from core.security import sanitize_for_prompt

if TYPE_CHECKING:
    from agents.strategist import TradeDecision

_SYSTEM_PROMPT = (
    "You are a contrarian investor and short-seller. You actively look for what "
    "the consensus is missing. You are comfortable being the only person in the room "
    "who disagrees. You look for overconfidence, narrative capture, and ignored tail risks. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)


@dataclass
class ContrarianReport:
    """Output from contrarian stress test."""

    agrees_with_consensus: bool
    veto: bool
    veto_confidence: float
    bear_case: str
    bull_case: str
    blind_spots: str


class ContrarianAgent(BaseAgent):
    """Devil's advocate — stress tests consensus and can veto trades."""

    AGENT_ID = "contrarian"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def stress_test(self, market: Market, consensus: "TradeDecision") -> ContrarianReport:
        """
        Argue against the consensus. Return ContrarianReport with optional veto.
        """
        safe_question = sanitize_for_prompt(market.question, "question")
        safe_memo = sanitize_for_prompt(consensus.investment_memo[:300], "memo")

        prompt = (
            f"Challenge this trading consensus:\n"
            f"Market: {safe_question}\n"
            f"Consensus action: {consensus.action}\n"
            f"Outcome: {consensus.outcome}\n"
            f"Confidence: {consensus.confidence:.2%}\n"
            f"Consensus score: {consensus.consensus_score:.3f}\n"
            f"Investment memo: {safe_memo}\n\n"
            "Your job is to argue the OPPOSITE side. Ask:\n"
            "1. What would have to be true for the crowd to be right and consensus wrong?\n"
            "2. What black swan scenarios are being ignored?\n"
            "3. What is the bear case? The bull case?\n"
            "4. What blind spots does the consensus have?\n"
            "5. If your confidence in the OPPOSITE direction is > 0.8, set veto=true\n\n"
            "Return JSON with keys: agrees_with_consensus (bool), veto (bool), "
            "veto_confidence (float 0-1), bear_case (string ≤200), "
            "bull_case (string ≤200), blind_spots (string ≤200). "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )

        raw = self._call_claude(_SYSTEM_PROMPT, prompt, max_tokens=1024)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            # Default to agreeing (no veto) on parse failure
            return ContrarianReport(
                agrees_with_consensus=True,
                veto=False,
                veto_confidence=0.0,
                bear_case="Parse failed.",
                bull_case="Parse failed.",
                blind_spots="Parse failed.",
            )

        veto_confidence = float(data.get("veto_confidence", 0.0))
        veto = bool(data.get("veto", False)) and veto_confidence > 0.8

        return ContrarianReport(
            agrees_with_consensus=bool(data.get("agrees_with_consensus", True)),
            veto=veto,
            veto_confidence=veto_confidence,
            bear_case=str(data.get("bear_case", "")),
            bull_case=str(data.get("bull_case", "")),
            blind_spots=str(data.get("blind_spots", "")),
        )

    def analyze(self, market: Market) -> AgentOpinion:
        """Standard analyze interface (not used directly in main loop)."""
        return self._safe_skip(market, "Contrarian is used via stress_test(), not analyze()")

    def report(self) -> str:
        return f"ContrarianAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
