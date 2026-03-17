"""
Model Router — selecteert het meest geschikte LLM op basis van het type vraag.

Routeringslogica:
┌─────────────────────────┬───────────────────────────────┬──────────────────────┐
│ Intent                  │ Ollama model                  │ Claude fallback       │
├─────────────────────────┼───────────────────────────────┼──────────────────────┤
│ SNELLE_TAAK             │ llama3.2:3b (snel + licht)    │ claude-haiku-4-5     │
│ TAAK_BEHEER             │ llama3.2 (tool-capable)       │ claude-haiku-4-5     │
│ PLANNING                │ qwen2.5:7b (redeneert goed)   │ claude-sonnet-4-6    │
│ MOTIVATIE               │ llama3.1:8b (conversationeel) │ claude-sonnet-4-6    │
│ COMPLEXE_ANALYSE        │ qwen2.5:14b (diep redeneren)  │ claude-opus-4-6      │
│ TECHNISCH               │ qwen2.5:7b                    │ claude-sonnet-4-6    │
└─────────────────────────┴───────────────────────────────┴──────────────────────┘
"""

from __future__ import annotations

import logging
import re
from enum import Enum, auto
from typing import Optional

from .llm.base import BaseLLMClient
from .llm.claude_client import ClaudeClient
from .llm.ollama_client import OllamaClient

logger = logging.getLogger(__name__)


class QueryIntent(Enum):
    SNELLE_TAAK = auto()       # "voeg toe", "markeer klaar", "verwijder"
    TAAK_BEHEER = auto()       # lijst opvragen, filteren, updaten
    PLANNING = auto()          # dag/week plannen, prioriteiten stellen
    MOTIVATIE = auto()         # aanmoedigen, streaks, doelen
    COMPLEXE_ANALYSE = auto()  # patronen analyseren, lange-termijn planning
    TECHNISCH = auto()         # technische vragen
    ALGEMEEN = auto()          # alles wat niet past


# Patroonherkenning per intent (Nederlandse sleutelwoorden)
_INTENT_PATTERNS: dict[QueryIntent, list[str]] = {
    QueryIntent.SNELLE_TAAK: [
        r"\b(voeg|voeg toe|maak|nieuw|new|add)\b",
        r"\b(klaar|gedaan|voltooid|done|compleet|af)\b",
        r"\b(verwijder|wis|delete|weg)\b",
    ],
    QueryIntent.TAAK_BEHEER: [
        r"\b(lijst|toon|laat zien|overzicht|wat staat|welke taken)\b",
        r"\b(update|verander|wijzig|pas aan|stel in)\b",
        r"\b(filter|categorie|prioriteit|hoog|medium|laag)\b",
    ],
    QueryIntent.PLANNING: [
        r"\b(plan|planning|agenda|schema|vandaag|morgen|week|maand)\b",
        r"\b(prioriteer|rangschik|beste volgorde|wanneer)\b",
        r"\b(strategie|aanpak|hoe pak ik)\b",
    ],
    QueryIntent.MOTIVATIE: [
        r"\b(motiveer|motivatie|aanmoedig|help me|ik voel|ik kan niet)\b",
        r"\b(streak|voortgang|prestatie|succes|trots|goed gedaan)\b",
        r"\b(lukt niet|moeilijk|uitgesteld|procrastinat)\b",
    ],
    QueryIntent.COMPLEXE_ANALYSE: [
        r"\b(analyseer|analyse|patroon|trend|inzicht|rapport)\b",
        r"\b(waarom|hoe komt|verklaar|vergelijk|verschil)\b",
        r"\b(diep|uitgebreid|gedetailleerd|volledig overzicht)\b",
    ],
    QueryIntent.TECHNISCH: [
        r"\b(code|programm|script|api|database|configureer|instel)\b",
        r"\b(error|fout|bug|werkt niet|probleem met)\b",
    ],
}

# Ollama-modellen per intent (meest geschikte voor die taak)
_OLLAMA_MODEL: dict[QueryIntent, str] = {
    QueryIntent.SNELLE_TAAK: "llama3.2:3b",
    QueryIntent.TAAK_BEHEER: "llama3.2",
    QueryIntent.PLANNING: "qwen2.5:7b",
    QueryIntent.MOTIVATIE: "llama3.1:8b",
    QueryIntent.COMPLEXE_ANALYSE: "qwen2.5:14b",
    QueryIntent.TECHNISCH: "qwen2.5:7b",
    QueryIntent.ALGEMEEN: "llama3.2",
}

# Claude-modellen per intent (fallback of expliciete keuze)
_CLAUDE_MODEL: dict[QueryIntent, str] = {
    QueryIntent.SNELLE_TAAK: "claude-haiku-4-5-20251001",
    QueryIntent.TAAK_BEHEER: "claude-haiku-4-5-20251001",
    QueryIntent.PLANNING: "claude-sonnet-4-6",
    QueryIntent.MOTIVATIE: "claude-sonnet-4-6",
    QueryIntent.COMPLEXE_ANALYSE: "claude-opus-4-6",
    QueryIntent.TECHNISCH: "claude-sonnet-4-6",
    QueryIntent.ALGEMEEN: "claude-sonnet-4-6",
}


def classify_intent(text: str) -> QueryIntent:
    """Bepaal de intent op basis van eenvoudige patroonherkenning (geen LLM-call nodig)."""
    lower = text.lower()
    scores: dict[QueryIntent, int] = {i: 0 for i in QueryIntent}

    for intent, patterns in _INTENT_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, lower):
                scores[intent] += 1

    best = max(scores, key=lambda i: scores[i])
    if scores[best] == 0:
        return QueryIntent.ALGEMEEN
    return best


class ModelRouter:
    """
    Kiest het juiste LLM-object op basis van intent en beschikbaarheid.
    Voorkeursvolgorde:
      1. Ollama (lokaal, gratis) indien beschikbaar
      2. Claude API als fallback
    """

    def __init__(self, prefer_ollama: bool = True):
        self._prefer_ollama = prefer_ollama
        self._ollama_available: Optional[bool] = None   # gecached na eerste check

    def _check_ollama(self) -> bool:
        if self._ollama_available is None:
            probe = OllamaClient()
            self._ollama_available = probe.is_available()
            if self._ollama_available:
                logger.info("Ollama beschikbaar op localhost:11434")
            else:
                logger.info("Ollama niet beschikbaar, gebruik Claude API.")
        return self._ollama_available

    def get_client(self, user_input: str) -> tuple[BaseLLMClient, QueryIntent]:
        """
        Geef een (client, intent)-tuple terug.
        De caller hoeft niet te weten welk model gebruikt wordt.
        """
        intent = classify_intent(user_input)
        client = self._select_client(intent)
        logger.debug("Intent=%s  →  model=%s", intent.name, client.model_name)
        return client, intent

    def _select_client(self, intent: QueryIntent) -> BaseLLMClient:
        if self._prefer_ollama and self._check_ollama():
            model = _OLLAMA_MODEL[intent]
            return OllamaClient(model=model)
        # Claude fallback
        model = _CLAUDE_MODEL[intent]
        return ClaudeClient(model=model)

    def get_claude_client(self, intent: QueryIntent) -> ClaudeClient:
        """Altijd Claude, ongeacht Ollama-beschikbaarheid (bijv. voor tool-use)."""
        return ClaudeClient(model=_CLAUDE_MODEL[intent])
