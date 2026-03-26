"""Factory for creating LLM providers from config."""

from __future__ import annotations

from src.llm.base import LLMProvider


def create_llm_provider(
    provider: str,
    api_key: str,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider instance based on provider name."""
    if provider == "anthropic":
        from src.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key)

    if provider == "openai":
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider
        return OpenAICompatibleProvider(api_key=api_key, base_url=base_url)

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. Supported: 'anthropic', 'openai'"
    )
