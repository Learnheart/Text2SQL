"""OpenAI-compatible LLM provider — supports Groq, Ollama, vLLM, OpenAI, etc."""

from __future__ import annotations

import json
import uuid
from typing import Any

from openai import OpenAI

from src.llm.base import LLMProvider, LLMResponse, ToolCall, ToolDefinition


class OpenAICompatibleProvider(LLMProvider):
    """LLM provider using OpenAI-compatible API."""

    def __init__(self, api_key: str, base_url: str | None = None) -> None:
        kwargs: dict[str, Any] = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)
        self._last_raw_response: Any = None

    def create(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[ToolDefinition] | None = None,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> LLMResponse:
        openai_messages = [{"role": "system", "content": system}]
        for msg in messages:
            openai_messages.append(self._convert_message(msg))

        kwargs: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": openai_messages,
        }
        if tools:
            kwargs["tools"] = [self._convert_tool_def(t) for t in tools]

        response = self._client.chat.completions.create(**kwargs)
        self._last_raw_response = response
        return self._normalize(response)

    def format_tool_result(self, *, tool_call_id: str, content: str) -> dict[str, Any]:
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": content,
        }

    def format_assistant_message(self, raw_response: Any) -> dict[str, Any]:
        choice = raw_response.choices[0]
        msg: dict[str, Any] = {"role": "assistant"}

        if choice.message.content:
            msg["content"] = choice.message.content

        if choice.message.tool_calls:
            msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in choice.message.tool_calls
            ]

        return msg

    @property
    def last_raw_response(self) -> Any:
        return self._last_raw_response

    @staticmethod
    def _convert_tool_def(tool: ToolDefinition) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            },
        }

    @staticmethod
    def _convert_message(msg: dict[str, Any]) -> dict[str, Any]:
        if isinstance(msg.get("content"), str):
            return msg

        content = msg.get("content", [])
        if isinstance(content, list) and content and isinstance(content[0], dict):
            if content[0].get("type") == "tool_result":
                return {
                    "role": "tool",
                    "tool_call_id": content[0].get("tool_use_id", ""),
                    "content": content[0].get("content", ""),
                }

        if msg.get("role") == "assistant" and isinstance(content, list):
            text_parts = []
            tool_calls = []
            for block in content:
                if hasattr(block, "type"):
                    if block.type == "text":
                        text_parts.append(block.text)
                    elif block.type == "tool_use":
                        tool_calls.append({
                            "id": block.id,
                            "type": "function",
                            "function": {
                                "name": block.name,
                                "arguments": json.dumps(block.input),
                            },
                        })

            result: dict[str, Any] = {"role": "assistant"}
            if text_parts:
                result["content"] = "\n".join(text_parts)
            if tool_calls:
                result["tool_calls"] = tool_calls
            return result

        return msg

    @staticmethod
    def _normalize(response: Any) -> LLMResponse:
        choice = response.choices[0]
        message = choice.message

        text = message.content
        tool_calls: list[ToolCall] = []

        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(
                    ToolCall(
                        id=tc.id or uuid.uuid4().hex[:12],
                        name=tc.function.name,
                        input=args,
                    )
                )

        stop_reason = "tool_use" if tool_calls else "end_turn"

        usage = response.usage
        return LLMResponse(
            text=text,
            tool_calls=tool_calls,
            stop_reason=stop_reason,
            input_tokens=usage.prompt_tokens if usage else 0,
            output_tokens=usage.completion_tokens if usage else 0,
        )
