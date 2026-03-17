"""
TaskAgent — persoonlijke 24/7 assistent.

Architectuur:
  - ModelRouter beslist welk LLM gebruikt wordt op basis van query-intent
  - Claude wordt altijd gebruikt voor tool-calls (betrouwbaarder dan lokale modellen)
  - Ollama wordt gebruikt voor conversationele antwoorden (sneller, gratis, privé)
  - ConversationStore persisteert alle berichten in SQLite
  - MotivationEngine verrijkt voltooide taken met aanmoedigingen
  - ReminderDaemon draait als achtergrond-thread
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Optional

import anthropic

from .database.store import ConversationStore, TaskStore
from .features.motivation import MotivationEngine
from .features.reminders import ReminderDaemon
from .llm.base import Message, LLMResponse
from .model_router import ModelRouter, QueryIntent
from .tools.task_tools import TASK_TOOLS, execute_tool

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """Je bent een persoonlijke 24/7 assistent die de gebruiker helpt zijn taken
te beheren, te plannen en te voltooien. Je spreekt altijd Nederlands.

Vandaag is het: {date}

Jouw karakter:
- Warm en motiverend, maar direct en to-the-point
- Je herinnert de gebruiker proactief aan deadlines en achterstallige taken
- Je viert voltooide taken enthousiast
- Je helpt bij het stellen van prioriteiten als de gebruiker overweldigd voelt
- Je stelt gerichte vragen als een verzoek onduidelijk is
- Je gebruikt emoji spaarzaam maar effectief

Gebruik tools voor alle taakbeheer-acties. Geef ALTIJD een menselijk antwoord
ná de tool-call — nooit alleen een ruwe tool-output.
"""

# Claude tool-definities (Anthropic-formaat, voor native tool_use)
_CLAUDE_TOOLS = [
    {
        "name": t.name,
        "description": t.description,
        "input_schema": t.parameters,
    }
    for t in TASK_TOOLS
]


class TaskAgent:
    """
    Persoonlijke taak-assistent met:
    - Dynamische LLM-selectie (Ollama voor chat, Claude voor tools)
    - Persistente gespreksgeschiedenis (SQLite)
    - Motivatie-berichten na voltooide taken
    - Achtergrond herinneringen-daemon
    """

    def __init__(self, prefer_ollama: bool = True):
        self._router = ModelRouter(prefer_ollama=prefer_ollama)
        self._motivation = MotivationEngine()
        self._daemon = ReminderDaemon(notify=self._print_notification)
        self._daemon.start()

        import os
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is niet ingesteld.")
        self._claude = anthropic.Anthropic(api_key=api_key)

    # ------------------------------------------------------------------
    # Publieke interface
    # ------------------------------------------------------------------

    def welcome(self) -> str:
        """Geeft de welkomstboodschap terug bij opstarten."""
        return self._motivation.welcome_message()

    def chat(self, user_input: str) -> str:
        """
        Verwerk één gebruikersbericht en geef een antwoord.
        Slaat alle berichten op in de database.
        """
        # Sla gebruikersbericht op
        ConversationStore.append("user", user_input)

        # Haal gespreksgeschiedenis op (laatste 20 berichten voor context)
        history = ConversationStore.recent(limit=20)

        # Bouw de berichten-lijst op voor de agentic loop
        messages = [{"role": m["role"], "content": m["content"]} for m in history]

        # Voer de agentic loop uit (altijd via Claude voor tool-gebruik)
        system = _SYSTEM_PROMPT.format(date=datetime.now().strftime("%A %d %B %Y"))
        response_text, used_model = self._agentic_loop(messages, system)

        # Sla antwoord op
        ConversationStore.append("assistant", response_text, model_used=used_model)

        return response_text

    def daily_briefing(self) -> str:
        return self._motivation.daily_briefing()

    def shutdown(self) -> None:
        self._daemon.stop()

    # ------------------------------------------------------------------
    # Agentic loop (Claude native tool_use)
    # ------------------------------------------------------------------

    def _agentic_loop(
        self,
        messages: list[dict],
        system: str,
        max_iterations: int = 6,
    ) -> tuple[str, str]:
        """
        Agentic loop met Claude native tool_use:
        1. Stuur berichten naar Claude
        2. Als Claude tools wil gebruiken: voer uit en voeg resultaten toe
        3. Herhaal totdat Claude klaar is

        Geeft (antwoord_tekst, model_naam) terug.
        """
        current_messages = list(messages)
        used_model = "claude-sonnet-4-6"
        completed_tool_calls: list[dict] = []

        for iteration in range(max_iterations):
            response = self._claude.messages.create(
                model=used_model,
                max_tokens=1024,
                system=system,
                tools=_CLAUDE_TOOLS,
                messages=current_messages,
            )
            used_model = response.model

            logger.debug(
                "[%d/%d] stop=%s blocks=%d",
                iteration + 1, max_iterations,
                response.stop_reason, len(response.content),
            )

            # Verzamel tekst-blokken
            text_blocks = [b.text for b in response.content if b.type == "text"]

            # Geen tool-calls → klaar
            if response.stop_reason == "end_turn":
                final_text = "\n".join(text_blocks).strip() or "Klaar."
                return self._enrich_with_motivation(final_text, completed_tool_calls), used_model

            # Tool-calls uitvoeren
            if response.stop_reason == "tool_use":
                current_messages.append({
                    "role": "assistant",
                    "content": response.content,
                })
                tool_results = []
                for block in response.content:
                    if block.type == "tool_use":
                        result = execute_tool(block.name, dict(block.input))
                        logger.debug("Tool %s → %s", block.name, result)
                        completed_tool_calls.append({
                            "name": block.name,
                            "input": dict(block.input),
                        })
                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": json.dumps(result, ensure_ascii=False),
                        })
                current_messages.append({"role": "user", "content": tool_results})
                continue

            # Onverwachte stop_reason
            return "\n".join(text_blocks).strip() or "Klaar.", used_model

        return "Maximale iteraties bereikt.", used_model

    # ------------------------------------------------------------------
    # Motivatie-verrijking
    # ------------------------------------------------------------------

    def _enrich_with_motivation(self, text: str, tool_calls: list[dict]) -> str:
        """Voeg motivatie-berichten toe na het voltooien van taken."""
        completed_tasks = []
        for tc in tool_calls:
            if tc["name"] == "complete_task":
                task_id = tc["input"].get("task_id", "")
                task = TaskStore.get(task_id)
                if task:
                    completed_tasks.append(task)

        if not completed_tasks:
            return text

        motivation_lines = []
        for task in completed_tasks:
            streak = task.get("streak_count", 0)
            motivation_lines.append(
                self._motivation.on_task_completed(task["title"], streak)
            )

        return text + "\n\n" + "\n".join(motivation_lines)

    # ------------------------------------------------------------------
    # Notification callback (voor ReminderDaemon)
    # ------------------------------------------------------------------

    @staticmethod
    def _print_notification(message: str) -> None:
        print(message, flush=True)
