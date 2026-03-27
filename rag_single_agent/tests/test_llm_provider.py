"""Tests for LLM provider abstraction layer."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from dataclasses import dataclass

import pytest

from src.llm.base import LLMProvider, LLMResponse, ToolCall
from src.llm.factory import create_llm_provider


# --- LLMResponse / ToolCall tests ---

class TestLLMResponse:
    def test_total_tokens(self):
        resp = LLMResponse(text="hi", input_tokens=100, output_tokens=50)
        assert resp.total_tokens == 150

    def test_has_tool_calls_true(self):
        resp = LLMResponse(
            text=None,
            tool_calls=[ToolCall(id="1", name="execute_sql", input={"sql": "SELECT 1"})],
            stop_reason="tool_use",
        )
        assert resp.has_tool_calls is True

    def test_has_tool_calls_false_end_turn(self):
        resp = LLMResponse(text="done", stop_reason="end_turn")
        assert resp.has_tool_calls is False

    def test_has_tool_calls_false_empty_tools(self):
        resp = LLMResponse(text=None, tool_calls=[], stop_reason="tool_use")
        assert resp.has_tool_calls is False

    def test_defaults(self):
        resp = LLMResponse(text="hello")
        assert resp.tool_calls == []
        assert resp.stop_reason == "end_turn"
        assert resp.input_tokens == 0
        assert resp.output_tokens == 0


class TestToolCall:
    def test_fields(self):
        tc = ToolCall(id="abc", name="execute_sql", input={"sql": "SELECT 1"})
        assert tc.id == "abc"
        assert tc.name == "execute_sql"
        assert tc.input == {"sql": "SELECT 1"}


# --- Factory tests ---

class TestFactory:
    @patch("src.llm.anthropic_provider.anthropic.Anthropic")
    def test_create_anthropic(self, mock_anthropic_cls):
        provider = create_llm_provider("anthropic", api_key="sk-ant-test")
        mock_anthropic_cls.assert_called_once_with(api_key="sk-ant-test")

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_create_openai(self, mock_openai_cls):
        provider = create_llm_provider("openai", api_key="sk-test", base_url="http://localhost:8000/v1")
        mock_openai_cls.assert_called_once_with(api_key="sk-test", base_url="http://localhost:8000/v1")

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_create_openai_no_base_url(self, mock_openai_cls):
        provider = create_llm_provider("openai", api_key="sk-test")
        mock_openai_cls.assert_called_once_with(api_key="sk-test")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown LLM provider"):
            create_llm_provider("unknown", api_key="test")


# --- AnthropicProvider tests ---

class TestAnthropicProvider:
    def _make_mock_response(self, *, text="Hello", tool_use=None, stop_reason="end_turn"):
        """Create a mock Anthropic response."""
        blocks = []
        if text:
            text_block = MagicMock()
            text_block.type = "text"
            text_block.text = text
            blocks.append(text_block)
        if tool_use:
            tool_block = MagicMock()
            tool_block.type = "tool_use"
            tool_block.id = tool_use["id"]
            tool_block.name = tool_use["name"]
            tool_block.input = tool_use["input"]
            blocks.append(tool_block)

        response = MagicMock()
        response.content = blocks
        response.stop_reason = stop_reason
        response.usage.input_tokens = 100
        response.usage.output_tokens = 50
        return response

    @patch("src.llm.anthropic_provider.anthropic.Anthropic")
    def test_create_text_response(self, mock_anthropic_cls):
        from src.llm.anthropic_provider import AnthropicProvider

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_mock_response(text="Hello world")

        provider = AnthropicProvider(api_key="test")
        resp = provider.create(
            system="You are helpful",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            model="claude-sonnet-4-6",
            max_tokens=4096,
            temperature=0.0,
        )

        assert resp.text == "Hello world"
        assert resp.stop_reason == "end_turn"
        assert resp.has_tool_calls is False
        assert resp.total_tokens == 150

    @patch("src.llm.anthropic_provider.anthropic.Anthropic")
    def test_create_tool_use_response(self, mock_anthropic_cls):
        from src.llm.anthropic_provider import AnthropicProvider

        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client
        mock_client.messages.create.return_value = self._make_mock_response(
            text=None,
            tool_use={"id": "tool_1", "name": "execute_sql", "input": {"sql": "SELECT 1"}},
            stop_reason="tool_use",
        )

        provider = AnthropicProvider(api_key="test")
        resp = provider.create(
            system="You are helpful",
            messages=[{"role": "user", "content": "Count rows"}],
            tools=[{"name": "execute_sql", "description": "Run SQL", "input_schema": {}}],
            model="claude-sonnet-4-6",
            max_tokens=4096,
            temperature=0.0,
        )

        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "execute_sql"
        assert resp.tool_calls[0].input == {"sql": "SELECT 1"}

    @patch("src.llm.anthropic_provider.anthropic.Anthropic")
    def test_format_tool_result(self, mock_anthropic_cls):
        from src.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(api_key="test")
        result = provider.format_tool_result(tool_call_id="tool_1", content='{"rows": []}')

        assert result == {
            "type": "tool_result",
            "tool_use_id": "tool_1",
            "content": '{"rows": []}',
        }

    @patch("src.llm.anthropic_provider.anthropic.Anthropic")
    def test_format_assistant_message(self, mock_anthropic_cls):
        from src.llm.anthropic_provider import AnthropicProvider

        mock_response = self._make_mock_response(text="Hello")
        provider = AnthropicProvider(api_key="test")
        msg = provider.format_assistant_message(mock_response)

        assert msg["role"] == "assistant"
        assert msg["content"] == mock_response.content

    @patch("src.llm.anthropic_provider.anthropic.Anthropic")
    def test_format_tool_results_message(self, mock_anthropic_cls):
        from src.llm.anthropic_provider import AnthropicProvider

        provider = AnthropicProvider(api_key="test")
        tool_results = [
            {"type": "tool_result", "tool_use_id": "t1", "content": "result1"},
            {"type": "tool_result", "tool_use_id": "t2", "content": "result2"},
        ]
        msgs = provider.format_tool_results_message(tool_results)

        assert len(msgs) == 1
        assert msgs[0]["role"] == "user"
        assert msgs[0]["content"] == tool_results


# --- OpenAICompatibleProvider tests ---

class TestOpenAICompatibleProvider:
    def _make_mock_response(self, *, content="Hello", tool_calls=None, finish_reason="stop"):
        """Create a mock OpenAI response."""
        message = MagicMock()
        message.content = content
        message.tool_calls = tool_calls

        choice = MagicMock()
        choice.message = message
        choice.finish_reason = finish_reason

        usage = MagicMock()
        usage.prompt_tokens = 80
        usage.completion_tokens = 40

        response = MagicMock()
        response.choices = [choice]
        response.usage = usage
        return response

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_create_text_response(self, mock_openai_cls):
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._make_mock_response(content="Hello world")

        provider = OpenAICompatibleProvider(api_key="test")
        resp = provider.create(
            system="You are helpful",
            messages=[{"role": "user", "content": "Hi"}],
            tools=[],
            model="llama-3.3-70b",
            max_tokens=4096,
            temperature=0.0,
        )

        assert resp.text == "Hello world"
        assert resp.stop_reason == "end_turn"
        assert resp.has_tool_calls is False
        assert resp.total_tokens == 120

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_create_tool_use_response(self, mock_openai_cls):
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider

        tc = MagicMock()
        tc.id = "call_1"
        tc.function.name = "execute_sql"
        tc.function.arguments = '{"sql": "SELECT 1"}'

        mock_client = MagicMock()
        mock_openai_cls.return_value = mock_client
        mock_client.chat.completions.create.return_value = self._make_mock_response(
            content=None,
            tool_calls=[tc],
            finish_reason="tool_calls",
        )

        provider = OpenAICompatibleProvider(api_key="test")
        resp = provider.create(
            system="You are helpful",
            messages=[{"role": "user", "content": "Count rows"}],
            tools=[{"name": "execute_sql", "description": "Run SQL", "input_schema": {}}],
            model="llama-3.3-70b",
            max_tokens=4096,
            temperature=0.0,
        )

        assert resp.has_tool_calls is True
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "execute_sql"
        assert resp.tool_calls[0].input == {"sql": "SELECT 1"}

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_convert_tool_def(self, mock_openai_cls):
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider

        internal = {
            "name": "execute_sql",
            "description": "Run SQL",
            "input_schema": {"type": "object", "properties": {"sql": {"type": "string"}}},
        }
        converted = OpenAICompatibleProvider._convert_tool_def(internal)

        assert converted == {
            "type": "function",
            "function": {
                "name": "execute_sql",
                "description": "Run SQL",
                "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}},
            },
        }

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_format_tool_result(self, mock_openai_cls):
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(api_key="test")
        result = provider.format_tool_result(tool_call_id="call_1", content='{"rows": []}')

        assert result == {
            "role": "tool",
            "tool_call_id": "call_1",
            "content": '{"rows": []}',
        }

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_format_tool_results_message(self, mock_openai_cls):
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider

        provider = OpenAICompatibleProvider(api_key="test")
        tool_results = [
            {"role": "tool", "tool_call_id": "c1", "content": "result1"},
            {"role": "tool", "tool_call_id": "c2", "content": "result2"},
        ]
        msgs = provider.format_tool_results_message(tool_results)

        assert len(msgs) == 2
        assert msgs[0]["role"] == "tool"
        assert msgs[1]["role"] == "tool"
        assert msgs is tool_results

    @patch("src.llm.openai_compatible_provider.OpenAI")
    def test_base_url_passed(self, mock_openai_cls):
        from src.llm.openai_compatible_provider import OpenAICompatibleProvider

        OpenAICompatibleProvider(api_key="gsk_test", base_url="https://api.groq.com/openai/v1")
        mock_openai_cls.assert_called_once_with(api_key="gsk_test", base_url="https://api.groq.com/openai/v1")
