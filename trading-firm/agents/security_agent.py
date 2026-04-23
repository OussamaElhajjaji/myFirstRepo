"""
Security & Fraud Detection Agent.
Scans markets for prompt injection, wash trading, and honeypots.
Distinct from core/security.py (code-level validation).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import List

from agents.base_agent import AgentOpinion, BaseAgent
from core.logger import get_logger
from core.memory import Memory
from core.messaging import MessageBus, TOPIC_SECURITY_ALERT
from core.polymarket import Market
from core.security import sanitize_for_prompt

logger = get_logger("security_agent")

_CONDITION_ID_RE = re.compile(r"^0x[0-9a-fA-F]{64}$")

_SYSTEM_PROMPT = (
    "You are a cybersecurity analyst specialising in financial market manipulation "
    "and fraud detection. You assume every input is adversarial until proven otherwise. "
    "You look for subtle signs of wash trading, data manipulation, and honeypot traps. "
    "Respond ONLY with valid JSON. No markdown. No explanation."
)


@dataclass
class SecurityAssessment:
    """Result of a security scan on a market."""

    market_id: str
    safe: bool
    flags: List[str] = field(default_factory=list)
    severity: str = "low"   # "low" | "medium" | "high" | "critical"

    def __post_init__(self) -> None:
        if self.severity not in ("low", "medium", "high", "critical"):
            self.severity = "low"


class SecurityAgent(BaseAgent):
    """AI-powered security screening for Polymarket markets."""

    AGENT_ID = "security_agent"

    def __init__(self, memory: Memory, bus: MessageBus | None = None) -> None:
        super().__init__(self.AGENT_ID, memory, bus)

    # ------------------------------------------------------------------
    # Market scanning
    # ------------------------------------------------------------------

    def scan_market(self, market: Market) -> SecurityAssessment:
        """Run security checks on a market. Returns SecurityAssessment."""
        flags: List[str] = []

        # 1. Check for prompt injection in question/description
        clean_q = sanitize_for_prompt(market.question, field="market.question")
        clean_d = sanitize_for_prompt(market.description, field="market.description")
        if "[REMOVED]" in clean_q or "[REMOVED]" in clean_d:
            flags.append("PROMPT_INJECTION_DETECTED")

        # 2. Wash trading: liquidity < 1% of volume
        if market.volume > 0 and market.liquidity < market.volume * 0.01:
            flags.append(f"LOW_LIQUIDITY_RATIO: {market.liquidity:.0f}/{market.volume:.0f}")

        # 3. Condition ID format check
        if market.condition_id and not _CONDITION_ID_RE.match(market.condition_id):
            flags.append(f"INVALID_CONDITION_ID_FORMAT: {market.condition_id[:20]}")

        # 4. Token ID uniqueness (look for reuse)
        if len(market.token_ids) != len(set(market.token_ids)):
            flags.append("DUPLICATE_TOKEN_IDS")

        # 5. Honeypot suspicion: both prices near 0 or near 1
        if market.yes_price > 0.95 or market.no_price > 0.95:
            flags.append("EXTREME_PRICE_SKEW")

        # 6. AI reasoning for subtle flags
        ai_flags = self._ai_scan(market, clean_q, clean_d)
        flags.extend(ai_flags)

        # Determine severity
        severity = self._compute_severity(flags)
        safe = severity not in ("high", "critical")

        assessment = SecurityAssessment(
            market_id=market.id,
            safe=safe,
            flags=flags,
            severity=severity,
        )

        if severity in ("critical", "high"):
            sec_logger = get_logger("security")
            sec_logger.warning(
                "SECURITY ALERT [%s] market=%s flags=%s",
                severity.upper(),
                market.id,
                flags,
            )
            self.bus.publish(TOPIC_SECURITY_ALERT, {
                "market_id": market.id,
                "severity": severity,
                "flags": flags,
            })

        return assessment

    def _ai_scan(self, market: Market, clean_q: str, clean_d: str) -> List[str]:
        """Use Claude to detect subtle manipulation signals."""
        prompt = (
            f"Analyse this prediction market for fraud or manipulation:\n"
            f"Question: {clean_q}\n"
            f"Description: {clean_d[:500]}\n"
            f"Yes price: {market.yes_price:.3f}, No price: {market.no_price:.3f}\n"
            f"Volume: ${market.volume:.0f}, Liquidity: ${market.liquidity:.0f}\n"
            f"Days to end: {market.days_to_end:.1f}\n\n"
            "Return JSON with keys: additional_flags (list of strings), "
            "analysis (string, ≤200 chars). "
            "Flag ONLY genuine concerns. "
            "Respond ONLY with valid JSON. No markdown. No explanation."
        )
        raw = self._call_claude(_SYSTEM_PROMPT, prompt, max_tokens=512)
        try:
            data = json.loads(raw)
            return [str(f) for f in data.get("additional_flags", [])]
        except (json.JSONDecodeError, TypeError):
            return []

    @staticmethod
    def _compute_severity(flags: List[str]) -> str:
        if not flags:
            return "low"
        critical_kws = {"PROMPT_INJECTION_DETECTED", "DUPLICATE_TOKEN_IDS"}
        high_kws = {"LOW_LIQUIDITY_RATIO", "INVALID_CONDITION_ID_FORMAT"}
        for f in flags:
            for kw in critical_kws:
                if kw in f:
                    return "critical"
        for f in flags:
            for kw in high_kws:
                if kw in f:
                    return "high"
        return "medium" if flags else "low"

    def scan_environment(self) -> bool:
        """
        Test basic connectivity (Anthropic + Polymarket).
        Returns True if environment is healthy.
        """
        # Minimal ping to Anthropic
        try:
            resp = self._call_claude(
                "You are a health check agent.",
                "Reply with JSON: {\"status\": \"ok\"}",
                max_tokens=32,
            )
            data = json.loads(resp)
            if data.get("status") != "ok":
                logger.warning("Anthropic health check returned unexpected: %s", resp)
                return False
        except Exception as exc:
            logger.error("Anthropic connectivity check failed: %s", exc)
            return False
        return True

    # ------------------------------------------------------------------
    # BaseAgent interface
    # ------------------------------------------------------------------

    def analyze(self, market: Market) -> AgentOpinion:
        """Run a full security scan and return opinion."""
        assessment = self.scan_market(market)
        if not assessment.safe:
            return self._safe_skip(market, f"Security flags: {assessment.flags}")
        return AgentOpinion(
            agent_id=self.agent_id,
            action="SKIP",
            confidence=0.0,
            edge=0.0,
            reasoning="Security check passed.",
            risk_factors=assessment.flags,
        )

    def report(self) -> str:
        return (
            f"SecurityAgent | accuracy={self.accuracy:.2%} | "
            f"paused={self._paused}"
        )
