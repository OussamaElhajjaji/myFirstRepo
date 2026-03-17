"""
Abstracte basis voor alle LLM-clients.
Elke implementatie (Claude, Ollama) volgt dit contract zodat de rest van de
applicatie volledig LLM-agnostisch is.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class Message:
    role: str   # "user" | "assistant" | "system"
    content: str


@dataclass
class ToolDefinition:
    name: str
    description: str
    parameters: dict   # JSON Schema object


@dataclass
class ToolResult:
    tool_use_id: str
    name: str
    output: Any


@dataclass
class LLMResponse:
    text: str
    stop_reason: str               # "end_turn" | "tool_use" | "stop"
    tool_calls: list[dict] = field(default_factory=list)
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


class BaseLLMClient(ABC):
    """Gedeelde interface voor alle LLM-backends."""

    @abstractmethod
    def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: Optional[list[ToolDefinition]] = None,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        """
        Stuur berichten naar het model en geef een genormaliseerde respons terug.
        Als `tools` opgegeven is, mag het model tool-calls teruggeven.
        """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Geef de naam van het actieve model terug (voor logging)."""
