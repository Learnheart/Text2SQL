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
# Each provider converts this to its own format.
ToolDefinition = dict[str, Any]


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All providers must normalize their responses into LLMResponse/ToolCall
    so the agent doesn't need to know which provider is being used.
    """

    @abstractmethod
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
        """Send a request to the LLM and return a normalized response."""
        ...

    @abstractmethod
    def format_tool_result(
        self,
        *,
        tool_call_id: str,
        content: str,
    ) -> dict[str, Any]:
        """Format a tool result for sending back to the LLM.

        Returns a dict in the provider's expected format.
        """
        ...

    @abstractmethod
    def format_assistant_message(self, raw_response: Any) -> dict[str, Any]:
        """Format the raw provider response as an assistant message for conversation history.

        The raw_response is the provider-specific response object (e.g., Anthropic Message,
        OpenAI ChatCompletion) that was used to build the LLMResponse.
        """
        ...

    @abstractmethod
    def format_tool_results_message(self, tool_results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Package tool results into messages for the conversation history.

        Anthropic: single user message with content = list of tool_result blocks.
        OpenAI/Groq: list of separate role='tool' messages.
        """
        ...
