"""Anthropic (Claude) LLM provider."""

from __future__ import annotations

from typing import Any

import anthropic

from src.llm.base import LLMProvider, LLMResponse, ToolCall, ToolDefinition


class AnthropicProvider(LLMProvider):
    """LLM provider using Anthropic's Claude API with native tool use."""

    def __init__(self, api_key: str) -> None:
        self._client = anthropic.Anthropic(api_key=api_key)
        self._last_raw_response: Any = None

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition],
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        """Call Claude API and return normalized response.

        Anthropic tool format is already our internal format:
        {name, description, input_schema}
        """
        response = self._client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=messages,
            tools=tools,
        )
        self._last_raw_response = response
        return self._normalize(response)

    def format_tool_result(self, *, tool_call_id: str, content: str) -> dict[str, Any]:
        """Anthropic format: {type: 'tool_result', tool_use_id, content}."""
        return {
            "type": "tool_result",
            "tool_use_id": tool_call_id,
            "content": content,
        }

    def format_assistant_message(self, raw_response: Any) -> dict[str, Any]:
        """Anthropic format: {role: 'assistant', content: response.content}."""
        return {"role": "assistant", "content": raw_response.content}

    @property
    def last_raw_response(self) -> Any:
        return self._last_raw_response

    @staticmethod
    def _normalize(response: anthropic.types.Message) -> LLMResponse:
        """Convert Anthropic response to normalized LLMResponse."""
        text_parts: list[str] = []
        tool_calls: list[ToolCall] = []

        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(id=block.id, name=block.name, input=block.input)
                )

        stop_reason = "tool_use" if response.stop_reason == "tool_use" else "end_turn"

        return LLMResponse(
            text="\n".join(text_parts) if text_parts else None,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )
