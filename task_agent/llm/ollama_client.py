"""
Ollama client — spreekt lokale modellen aan via de Ollama REST API.
Ondersteunt tool-calling via modellen die dat beheersen (llama3.2, qwen2.5, etc.)
met een JSON-fallback voor modellen zonder native tool support.
"""

from __future__ import annotations

import json
import logging
from typing import Optional

import requests

from .base import BaseLLMClient, LLMResponse, Message, ToolDefinition

logger = logging.getLogger(__name__)

_OLLAMA_BASE = "http://localhost:11434"

# Modellen die native tool-calling ondersteunen via Ollama
_TOOL_CAPABLE_MODELS = {
    "llama3.2", "llama3.2:3b", "llama3.1", "llama3.1:8b",
    "qwen2.5", "qwen2.5:7b", "qwen2.5:14b",
    "mistral", "mistral:7b", "mistral-nemo",
}


class OllamaClient(BaseLLMClient):

    def __init__(self, model: str = "llama3.2"):
        self._model = model
        self._base_url = _OLLAMA_BASE

    @property
    def model_name(self) -> str:
        return self._model

    def is_available(self) -> bool:
        try:
            r = requests.get(f"{self._base_url}/api/tags", timeout=3)
            return r.status_code == 200
        except requests.ConnectionError:
            return False

    def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: Optional[list[ToolDefinition]] = None,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        if self._supports_tools() and tools:
            return self._chat_with_tools(messages, system, tools, max_tokens)
        return self._chat_plain(messages, system, tools, max_tokens)

    # ------------------------------------------------------------------
    # Native tool-calling (Ollama /api/chat met tools)
    # ------------------------------------------------------------------

    def _chat_with_tools(
        self,
        messages: list[Message],
        system: str,
        tools: list[ToolDefinition],
        max_tokens: int,
    ) -> LLMResponse:
        payload = {
            "model": self._model,
            "messages": self._build_messages(messages, system),
            "tools": [self._to_ollama_tool(t) for t in tools],
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        response = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        msg = data.get("message", {})

        text = msg.get("content", "")
        tool_calls = []

        for tc in msg.get("tool_calls", []):
            fn = tc.get("function", {})
            tool_calls.append({
                "id": f"ollama_{fn.get('name', 'unknown')}",
                "name": fn.get("name", ""),
                "input": fn.get("arguments", {}),
            })

        stop_reason = "tool_use" if tool_calls else "end_turn"
        return LLMResponse(
            text=text,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            model=self._model,
        )

    # ------------------------------------------------------------------
    # JSON-gebaseerde tool-calling als fallback
    # ------------------------------------------------------------------

    def _chat_plain(
        self,
        messages: list[Message],
        system: str,
        tools: Optional[list[ToolDefinition]],
        max_tokens: int,
    ) -> LLMResponse:
        full_system = system
        if tools:
            full_system += self._tools_to_system_prompt(tools)

        payload = {
            "model": self._model,
            "messages": self._build_messages(messages, full_system),
            "stream": False,
            "options": {"num_predict": max_tokens},
        }

        response = requests.post(
            f"{self._base_url}/api/chat",
            json=payload,
            timeout=120,
        )
        response.raise_for_status()
        data = response.json()
        raw = data.get("message", {}).get("content", "")

        tool_calls = self._extract_json_tool_calls(raw) if tools else []
        stop_reason = "tool_use" if tool_calls else "end_turn"
        clean_text = self._strip_json_block(raw) if tool_calls else raw

        return LLMResponse(
            text=clean_text,
            stop_reason=stop_reason,
            tool_calls=tool_calls,
            model=self._model,
        )

    # ------------------------------------------------------------------
    # Hulpfuncties
    # ------------------------------------------------------------------

    def _supports_tools(self) -> bool:
        base = self._model.split(":")[0]
        return base in _TOOL_CAPABLE_MODELS or self._model in _TOOL_CAPABLE_MODELS

    def _build_messages(self, messages: list[Message], system: str) -> list[dict]:
        result = []
        if system:
            result.append({"role": "system", "content": system})
        for m in messages:
            result.append({"role": m.role, "content": m.content})
        return result

    @staticmethod
    def _to_ollama_tool(tool: ToolDefinition) -> dict:
        return {
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        }

    @staticmethod
    def _tools_to_system_prompt(tools: list[ToolDefinition]) -> str:
        lines = [
            "\n\nAls je een tool wil gebruiken, antwoord dan met ALLEEN een geldig JSON-object:",
            '{"tool": "<naam>", "input": {<parameters>}}',
            "\nBeschikbare tools:",
        ]
        for t in tools:
            props = ", ".join(t.parameters.get("properties", {}).keys())
            lines.append(f"- {t.name}({props}): {t.description}")
        return "\n".join(lines)

    @staticmethod
    def _extract_json_tool_calls(text: str) -> list[dict]:
        import re
        pattern = r'\{[^{}]*"tool"\s*:\s*"([^"]+)"[^{}]*"input"\s*:\s*(\{[^{}]*\})[^{}]*\}'
        matches = re.findall(pattern, text, re.DOTALL)
        calls = []
        for name, input_str in matches:
            try:
                calls.append({
                    "id": f"json_{name}",
                    "name": name,
                    "input": json.loads(input_str),
                })
            except json.JSONDecodeError:
                logger.warning("Kon tool-call JSON niet parsen: %s", input_str)
        return calls

    @staticmethod
    def _strip_json_block(text: str) -> str:
        import re
        return re.sub(r'\{[^{}]*"tool"\s*:[^{}]*\}', "", text).strip()
