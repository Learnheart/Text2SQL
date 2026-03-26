"""LLM Provider abstraction — normalized interface for any LLM backend."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """Normalized tool call from any LLM provider."""

    id: str
    name: str
    input: dict[str, Any]


@dataclass
class LLMResponse:
    """Normalized LLM response from any provider."""

    text: str | None
    tool_calls: list[ToolCall] = field(default_factory=list)
    stop_reason: str = "end_turn"  # "end_turn" | "tool_use"
    input_tokens: int = 0
    output_tokens: int = 0

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens

    @property
    def has_tool_calls(self) -> bool:
        return self.stop_reason == "tool_use" and len(self.tool_calls) > 0


# Normalized tool definition format (internal representation).
ToolDefinition = dict[str, Any]


class LLMProvider(ABC):
    """Abstract base class for LLM providers."""

    @abstractmethod
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
        """Send a request to the LLM and return a normalized response."""
        ...

    @abstractmethod
    def format_tool_result(
        self,
        *,
        tool_call_id: str,
        content: str,
    ) -> dict[str, Any]:
        """Format a tool result for sending back to the LLM."""
        ...

    @abstractmethod
    def format_assistant_message(self, raw_response: Any) -> dict[str, Any]:
        """Format the raw provider response as an assistant message."""
        ...
