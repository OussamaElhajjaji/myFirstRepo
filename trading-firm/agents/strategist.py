"""
Chief Strategist (Orchestrator) Agent.
Reads all opinions, runs weighted consensus, makes the final trade decision.
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from agents.base_agent import AgentOpinion, BaseAgent
from core.config import get_config
from core.memory import Memory
from core.messaging import MessageBus, TOPIC_CONSENSUS_REACHED
from core.polymarket import Market
from core.security import sanitize_for_prompt, validate_action, validate_outcome

_SYSTEM_PROMPT = (
    "You are the chief portfolio manager of a quantitative trading firm. "
    "You receive opinions from your team of analysts and synthesise them into a final decision. "
    "You value process over instinct. You never trade on one opinion alone. "
    "You write clear investment memos. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)


@dataclass
class TradeDecision:
    """Final trade decision from the strategist."""

    action: str           # "BUY_YES" | "BUY_NO" | "SKIP"
    outcome: str          # "YES" | "NO" | ""
    size_usd: float
    confidence: float
    consensus_score: float
    market_id: str = ""
    agent_breakdown: Dict[str, str] = field(default_factory=dict)
    investment_memo: str = ""

    def __post_init__(self) -> None:
        self.action = validate_action(self.action)
        self.confidence = max(0.0, min(1.0, self.confidence))
        self.size_usd = max(0.0, self.size_usd)


class StrategistAgent(BaseAgent):
    """Chief strategist — orchestrates consensus across all agent opinions."""

    AGENT_ID = "strategist"

    def __init__(self, memory: Memory, bus: Optional[MessageBus] = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    def analyze_all(self, market: Market, opinions: List[AgentOpinion]) -> TradeDecision:
        """
        Synthesise all agent opinions into a final trade decision.
        Uses weighted consensus (weight = accuracy of each agent).
        """
        cfg = get_config()

        if not opinions:
            return self._skip_decision(market.id, "No opinions received")

        # --- Weighted consensus ---
        direction_map = {"BUY_YES": 1.0, "BUY_NO": -1.0, "SKIP": 0.0}
        total_weight = 0.0
        weighted_sum = 0.0
        agent_breakdown: Dict[str, str] = {}

        for opinion in opinions:
            accuracy = self.memory.get_agent_accuracy(opinion.agent_id)
            # Clamp accuracy between 0.1 and 1.0 (avoid zero weight)
            weight = max(0.1, accuracy)
            direction = direction_map.get(opinion.action, 0.0)
            weighted_sum += opinion.confidence * weight * direction
            total_weight += weight
            agent_breakdown[opinion.agent_id] = (
                f"{opinion.action}@{opinion.confidence:.2f}"
            )

        consensus_score = weighted_sum / total_weight if total_weight > 0 else 0.0

        # --- Check minimum consensus threshold ---
        if abs(consensus_score) < cfg.min_consensus_score:
            return self._skip_decision(
                market.id,
                f"Consensus score {consensus_score:.3f} below threshold {cfg.min_consensus_score}",
                agent_breakdown,
            )

        # --- Check disagreement (standard deviation of confidences) ---
        confidences = [o.confidence for o in opinions if o.action != "SKIP"]
        if len(confidences) >= 2:
            mean_c = sum(confidences) / len(confidences)
            variance = sum((c - mean_c) ** 2 for c in confidences) / len(confidences)
            std_dev = math.sqrt(variance)
            if std_dev > 0.35:
                return self._skip_decision(
                    market.id,
                    f"High disagreement among agents (std_dev={std_dev:.3f})",
                    agent_breakdown,
                )

        # --- Determine action and outcome ---
        if consensus_score > 0:
            action = "BUY_YES"
            outcome = "YES"
            price = market.yes_price
        else:
            action = "BUY_NO"
            outcome = "NO"
            price = market.no_price

        avg_confidence = abs(consensus_score)
        avg_edge = sum(o.edge for o in opinions) / len(opinions) if opinions else 0.0

        # --- Kelly-adjusted sizing ---
        size_usd = self._kelly_size(avg_confidence, avg_edge, price)

        # --- Build investment memo ---
        memo = self._build_memo(market, opinions, consensus_score, size_usd)

        # --- Ask Claude for synthesis ---
        final_decision = self._ai_synthesise(
            market, opinions, consensus_score, action, outcome, size_usd, memo
        )

        self.bus.publish(TOPIC_CONSENSUS_REACHED, {
            "market_id": market.id,
            "action": final_decision.action,
            "consensus_score": final_decision.consensus_score,
            "size_usd": final_decision.size_usd,
            "agent_breakdown": agent_breakdown,
        })

        return final_decision

    def _kelly_size(self, confidence: float, edge: float, price: float) -> float:
        """Calculate Kelly-fractioned position size."""
        cfg = get_config()
        if price <= 0 or price >= 1:
            return cfg.max_position_usd * 0.1

        # Kelly fraction = (p - q) / b
        # p = win probability (confidence), q = 1-p, b = (1/price - 1)
        b = (1.0 / price) - 1.0
        q = 1.0 - confidence
        kelly = (confidence - q / b) if b > 0 else 0.0
        kelly = max(0.0, min(0.25, kelly))  # cap at 25% Kelly

        size = kelly * cfg.max_position_usd
        return max(1.0, min(size, cfg.max_position_usd))

    def _build_memo(
        self,
        market: Market,
        opinions: List[AgentOpinion],
        consensus_score: float,
        size_usd: float,
    ) -> str:
        """Build a structured investment memo."""
        lines = [
            f"Market: {market.question[:100]}",
            f"Consensus: {consensus_score:+.3f}",
            f"Proposed size: ${size_usd:.2f}",
            "Agent opinions:",
        ]
        for op in opinions:
            lines.append(
                f"  {op.agent_id}: {op.action} (conf={op.confidence:.2f}, edge={op.edge:.3f})"
            )
            if op.risk_factors:
                lines.append(f"    Risks: {', '.join(op.risk_factors[:3])}")
        return "\n".join(lines)

    def _ai_synthesise(
        self,
        market: Market,
        opinions: List[AgentOpinion],
        consensus_score: float,
        action: str,
        outcome: str,
        size_usd: float,
        memo: str,
    ) -> TradeDecision:
        """Use Claude to write a final investment memo and validate decision."""
        safe_q = sanitize_for_prompt(market.question, "question")
        agent_breakdown: Dict[str, str] = {
            o.agent_id: f"{o.action}@{o.confidence:.2f}" for o in opinions
        }

        prompt = (
            f"Synthesise this trading team's opinions into a final decision:\n"
            f"Market: {safe_q}\n"
            f"Preliminary consensus: {action} (score: {consensus_score:+.3f})\n"
            f"Proposed size: ${size_usd:.2f}\n"
            f"Proposed outcome: {outcome}\n\n"
            f"Team opinions:\n"
        )
        for op in opinions:
            prompt += (
                f"- {op.agent_id}: {op.action}, conf={op.confidence:.2f}, "
                f"edge={op.edge:.3f}, reasons: {sanitize_for_prompt(op.reasoning[:100], 'reasoning')}\n"
            )
        prompt += (
            "\nWrite a concise investment memo (≤200 chars) and confirm or override the decision.\n"
            "Return JSON with keys: action (BUY_YES|BUY_NO|SKIP), outcome (YES|NO|empty), "
            "confidence (0-1), size_usd (float), consensus_score (float), "
            "investment_memo (string). "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )

        raw = self._call_claude(_SYSTEM_PROMPT, prompt, max_tokens=1024)
        try:
            data = json.loads(raw)
            final_action = validate_action(data.get("action", action))
            final_outcome = ""
            if final_action != "SKIP":
                try:
                    final_outcome = validate_outcome(data.get("outcome", outcome))
                except ValueError:
                    final_outcome = outcome
            decision = TradeDecision(
                action=final_action,
                outcome=final_outcome,
                size_usd=float(data.get("size_usd", size_usd)),
                confidence=float(data.get("confidence", abs(consensus_score))),
                consensus_score=float(data.get("consensus_score", consensus_score)),
                market_id=market.id,
                agent_breakdown=agent_breakdown,
                investment_memo=str(data.get("investment_memo", memo[:200])),
            )
        except (json.JSONDecodeError, TypeError, ValueError):
            decision = TradeDecision(
                action=action,
                outcome=outcome,
                size_usd=size_usd,
                confidence=abs(consensus_score),
                consensus_score=consensus_score,
                market_id=market.id,
                agent_breakdown=agent_breakdown,
                investment_memo=memo[:200],
            )

        # Persist memo to memory
        self.memory.remember(
            self.AGENT_ID,
            f"memo_{market.id}",
            decision.investment_memo,
            ttl_hours=168,
        )

        return decision

    def _skip_decision(
        self,
        market_id: str,
        reason: str,
        agent_breakdown: Optional[Dict] = None,
    ) -> TradeDecision:
        return TradeDecision(
            action="SKIP",
            outcome="",
            size_usd=0.0,
            confidence=0.0,
            consensus_score=0.0,
            market_id=market_id,
            agent_breakdown=agent_breakdown or {},
            investment_memo=reason,
        )

    def analyze(self, market: Market) -> AgentOpinion:
        """Standard analyze interface (not used directly — use analyze_all)."""
        return self._safe_skip(market, "Strategist is used via analyze_all(), not analyze()")

    def report(self) -> str:
        return f"StrategistAgent | accuracy={self.accuracy:.2%} | paused={self._paused}"
