"""
Anthropic Claude client — gebruikt native tool_use API.
"""

from __future__ import annotations

import os
from typing import Optional

import anthropic

from .base import BaseLLMClient, LLMResponse, Message, ToolDefinition


class ClaudeClient(BaseLLMClient):

    def __init__(self, model: str = "claude-sonnet-4-6"):
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise EnvironmentError("ANTHROPIC_API_KEY is niet ingesteld.")
        self._client = anthropic.Anthropic(api_key=api_key)
        self._model = model

    @property
    def model_name(self) -> str:
        return self._model

    def chat(
        self,
        messages: list[Message],
        system: str = "",
        tools: Optional[list[ToolDefinition]] = None,
        max_tokens: int = 2048,
    ) -> LLMResponse:
        api_messages = [{"role": m.role, "content": m.content} for m in messages]
        kwargs: dict = {
            "model": self._model,
            "max_tokens": max_tokens,
            "messages": api_messages,
        }
        if system:
            kwargs["system"] = system
        if tools:
            kwargs["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        response = self._client.messages.create(**kwargs)

        text_parts = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })

        return LLMResponse(
            text=" ".join(text_parts),
            stop_reason=response.stop_reason or "end_turn",
            tool_calls=tool_calls,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
