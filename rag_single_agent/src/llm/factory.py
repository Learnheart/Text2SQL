"""Factory for creating LLM providers from config."""

from __future__ import annotations

from src.llm.base import LLMProvider


def create_llm_provider(
    provider: str,
    api_key: str,
    base_url: str | None = None,
) -> LLMProvider:
    """Create an LLM provider instance based on provider name.

    Args:
        provider: Provider name — 'anthropic' or 'openai'
        api_key: API key for the provider
        base_url: Optional base URL override (for Groq, Ollama, vLLM, etc.)

    Provider examples:
        Anthropic Claude:  provider='anthropic', api_key='sk-ant-...'
        OpenAI GPT-4o:     provider='openai', api_key='sk-...'
        Groq:              provider='openai', api_key='gsk_...', base_url='https://api.groq.com/openai/v1'
        Ollama:            provider='openai', api_key='ollama', base_url='http://localhost:11434/v1'
        vLLM:              provider='openai', api_key='EMPTY', base_url='http://localhost:8000/v1'
    """
    if provider == "anthropic":
        from src.llm.anthropic_provider import AnthropicProvider
        return AnthropicProvider(api_key=api_key)

    if provider == "openai":
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider
        return OpenAICompatibleProvider(api_key=api_key, base_url=base_url)

    raise ValueError(
        f"Unknown LLM provider: '{provider}'. Supported: 'anthropic', 'openai'"
    )
