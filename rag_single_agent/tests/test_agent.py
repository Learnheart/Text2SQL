"""Tests for Agent core: tool use loop, dispatch, response building."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schemas import AgentResponse, RAGContext, MetricDef, Example, ToolCallRecord
from src.agent.agent import Agent
from src.agent.response_parser import format_response_for_api


# ---------------------------------------------------------------------------
# Helpers to build mock Claude API responses
# ---------------------------------------------------------------------------

def _text_block(text: str):
    return SimpleNamespace(type="text", text=text)


def _tool_use_block(tool_id: str, name: str, input_: dict):
    return SimpleNamespace(type="tool_use", id=tool_id, name=name, input=input_)


def _usage(inp: int = 100, out: int = 50):
    return SimpleNamespace(input_tokens=inp, output_tokens=out)


def _message(stop_reason: str, content: list, usage=None):
    return SimpleNamespace(
        stop_reason=stop_reason,
        content=content,
        usage=usage or _usage(),
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_deps():
    """Create mocked dependencies for Agent."""
    db_pool = MagicMock()
    embedding_service = MagicMock()
    vector_store = MagicMock()
    semantic_layer = MagicMock()

    rag_retrieval = MagicMock()
    rag_retrieval.retrieve.return_value = RAGContext(
        schema_chunks=["Table: sales (id, total_amount, merchant_id, status)"],
        examples=[Example(question="Total revenue?", sql="SELECT SUM(total_amount) FROM sales")],
        metrics=[MetricDef(name="doanh_thu", sql="SUM(sales.total_amount)")],
    )

    prompt_builder = MagicMock()
    prompt_builder.build.return_value = "You are a SQL agent..."

    return {
        "db_pool": db_pool,
        "embedding_service": embedding_service,
        "vector_store": vector_store,
        "semantic_layer": semantic_layer,
        "rag_retrieval": rag_retrieval,
        "prompt_builder": prompt_builder,
    }


@pytest.fixture
def agent(mock_deps):
    """Create Agent with mocked deps and mocked Anthropic client."""
    with patch("src.agent.agent.anthropic.Anthropic") as mock_cls:
        a = Agent(**mock_deps)
        # Expose the mock client for per-test configuration
        a._mock_client = mock_cls.return_value
        return a


# ---------------------------------------------------------------------------
# Tests — Happy path
# ---------------------------------------------------------------------------

class TestAgentHappyPath:
    @pytest.mark.asyncio
    async def test_single_tool_call_success(self, agent):
        """Question → execute_sql tool call → final response with results."""
        # First API call: agent wants to call execute_sql
        tool_call_response = _message(
            stop_reason="tool_use",
            content=[
                _text_block("Let me query the database."),
                _tool_use_block("tc_1", "execute_sql", {"sql": "SELECT SUM(total_amount) FROM sales"}),
            ],
        )

        # Second API call: agent provides final answer
        final_response = _message(
            stop_reason="end_turn",
            content=[_text_block("Total revenue is 1,000,000 VND.")],
        )

        agent._client.messages.create = MagicMock(side_effect=[tool_call_response, final_response])

        # Mock execute_sql tool
        with patch("src.agent.agent.execute_sql", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {
                "columns": ["sum"],
                "rows": [[1000000]],
                "row_count": 1,
            }
            result = await agent.run("Tổng doanh thu?")

        assert isinstance(result, AgentResponse)
        assert result.status == "success"
        assert result.sql == "SELECT SUM(total_amount) FROM sales"
        assert result.results["row_count"] == 1
        assert result.total_tokens == 300  # 2 calls × 150 tokens each
        assert len(result.tool_calls) == 1
        assert result.tool_calls[0].tool_name == "execute_sql"
        assert result.latency_ms >= 0

    @pytest.mark.asyncio
    async def test_multi_tool_calls(self, agent):
        """Agent calls search_schema, then get_metric, then execute_sql."""
        # Call 1: search_schema
        resp1 = _message("tool_use", content=[
            _tool_use_block("tc_1", "search_schema", {"query": "merchant tables"}),
        ])
        # Call 2: get_metric_definition
        resp2 = _message("tool_use", content=[
            _tool_use_block("tc_2", "get_metric_definition", {"metric_name": "doanh_thu"}),
        ])
        # Call 3: execute_sql
        resp3 = _message("tool_use", content=[
            _tool_use_block("tc_3", "execute_sql", {"sql": "SELECT SUM(total_amount) FROM sales"}),
        ])
        # Call 4: final answer
        resp4 = _message("end_turn", content=[_text_block("Here are the results.")])

        agent._client.messages.create = MagicMock(side_effect=[resp1, resp2, resp3, resp4])

        with patch("src.agent.agent.search_schema", new_callable=AsyncMock) as mock_search, \
             patch("src.agent.agent.get_metric_definition", new_callable=AsyncMock) as mock_metric, \
             patch("src.agent.agent.execute_sql", new_callable=AsyncMock) as mock_exec:
            mock_search.return_value = {"results": [{"content": "merchants table"}]}
            mock_metric.return_value = {"name": "doanh_thu", "sql": "SUM(sales.total_amount)"}
            mock_exec.return_value = {"columns": ["sum"], "rows": [[500000]], "row_count": 1}

            result = await agent.run("Top merchant revenue?")

        assert result.status == "success"
        assert len(result.tool_calls) == 3
        assert result.tool_calls[0].tool_name == "search_schema"
        assert result.tool_calls[1].tool_name == "get_metric_definition"
        assert result.tool_calls[2].tool_name == "execute_sql"


# ---------------------------------------------------------------------------
# Tests — Out of scope / no tool calls
# ---------------------------------------------------------------------------

class TestAgentOutOfScope:
    @pytest.mark.asyncio
    async def test_out_of_scope_question(self, agent):
        """Non-data question → agent responds without calling any tool."""
        final = _message("end_turn", content=[
            _text_block("Xin lỗi, tôi chỉ hỗ trợ câu hỏi về dữ liệu Banking/POS."),
        ])
        agent._client.messages.create = MagicMock(return_value=final)

        result = await agent.run("Thời tiết hôm nay thế nào?")

        assert result.status == "out_of_scope"
        assert result.sql is None
        assert result.results is None
        assert len(result.tool_calls) == 0
        assert "Banking/POS" in result.explanation or "xin lỗi" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_greeting(self, agent):
        """Greeting → friendly response, no tools."""
        final = _message("end_turn", content=[
            _text_block("Xin chào! Tôi có thể giúp bạn truy vấn dữ liệu Banking/POS."),
        ])
        agent._client.messages.create = MagicMock(return_value=final)

        result = await agent.run("Xin chào")

        assert result.status == "out_of_scope"
        assert result.sql is None
        assert len(result.tool_calls) == 0


# ---------------------------------------------------------------------------
# Tests — Error recovery
# ---------------------------------------------------------------------------

class TestAgentErrorRecovery:
    @pytest.mark.asyncio
    async def test_sql_error_then_retry(self, agent):
        """Agent generates bad SQL → gets error → retries with corrected SQL → success."""
        # Call 1: agent tries bad SQL
        resp1 = _message("tool_use", content=[
            _tool_use_block("tc_1", "execute_sql", {"sql": "SELECT * FROM nonexistent_table"}),
        ])
        # Call 2: agent retries with corrected SQL
        resp2 = _message("tool_use", content=[
            _text_block("The table doesn't exist. Let me use the correct table name."),
            _tool_use_block("tc_2", "execute_sql", {"sql": "SELECT * FROM sales LIMIT 10"}),
        ])
        # Call 3: final answer
        resp3 = _message("end_turn", content=[_text_block("Here are the sales records.")])

        agent._client.messages.create = MagicMock(side_effect=[resp1, resp2, resp3])

        call_count = 0

        async def mock_exec(sql, pool):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": 'relation "nonexistent_table" does not exist'}
            return {"columns": ["id", "total_amount"], "rows": [[1, 100]], "row_count": 1}

        with patch("src.agent.agent.execute_sql", side_effect=mock_exec):
            result = await agent.run("Show me recent sales")

        assert result.status == "success"
        assert len(result.tool_calls) == 2
        assert "error" in str(result.tool_calls[0].tool_output)
        assert result.tool_calls[1].tool_output["row_count"] == 1


# ---------------------------------------------------------------------------
# Tests — Max tool calls
# ---------------------------------------------------------------------------

class TestAgentMaxToolCalls:
    @pytest.mark.asyncio
    async def test_max_tool_calls_reached(self, agent):
        """Agent keeps calling tools until hitting the limit."""
        # Create a response that always wants another tool call
        tool_response = _message("tool_use", content=[
            _tool_use_block("tc_loop", "search_schema", {"query": "something"}),
        ])
        agent._client.messages.create = MagicMock(return_value=tool_response)

        with patch("src.agent.agent.search_schema", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"results": []}
            # Temporarily lower max tool calls for faster test
            original = agent._client  # preserve ref
            with patch("src.config.settings.agent_max_tool_calls", 3):
                result = await agent.run("Infinite loop question")

        assert result.status == "error"
        assert "Maximum tool calls" in result.explanation


# ---------------------------------------------------------------------------
# Tests — _dispatch_tool
# ---------------------------------------------------------------------------

class TestDispatchTool:
    @pytest.mark.asyncio
    async def test_dispatch_execute_sql(self, agent):
        with patch("src.agent.agent.execute_sql", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"columns": [], "rows": [], "row_count": 0}
            result = await agent._dispatch_tool("execute_sql", {"sql": "SELECT 1"})
            mock_fn.assert_called_once_with("SELECT 1", agent._pool)
            assert result["row_count"] == 0

    @pytest.mark.asyncio
    async def test_dispatch_search_schema(self, agent):
        with patch("src.agent.agent.search_schema", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"results": []}
            result = await agent._dispatch_tool("search_schema", {"query": "test"})
            mock_fn.assert_called_once_with("test", agent._embedder, agent._vector_store)

    @pytest.mark.asyncio
    async def test_dispatch_get_metric(self, agent):
        with patch("src.agent.agent.get_metric_definition", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"name": "doanh_thu", "sql": "SUM(...)"}
            result = await agent._dispatch_tool("get_metric_definition", {"metric_name": "doanh_thu"})
            mock_fn.assert_called_once_with("doanh_thu", agent._semantic_layer)

    @pytest.mark.asyncio
    async def test_dispatch_get_column_values(self, agent):
        with patch("src.agent.agent.get_column_values", new_callable=AsyncMock) as mock_fn:
            mock_fn.return_value = {"values": ["completed", "pending"]}
            result = await agent._dispatch_tool(
                "get_column_values", {"table": "sales", "column": "status"}
            )
            mock_fn.assert_called_once_with("sales", "status", agent._pool, agent._semantic_layer)

    @pytest.mark.asyncio
    async def test_dispatch_unknown_tool(self, agent):
        result = await agent._dispatch_tool("nonexistent_tool", {})
        assert "error" in result
        assert "Unknown tool" in result["error"]


# ---------------------------------------------------------------------------
# Tests — _build_response
# ---------------------------------------------------------------------------

class TestBuildResponse:
    def test_success_response(self, agent):
        tool_calls = [
            ToolCallRecord(
                tool_name="execute_sql",
                tool_input={"sql": "SELECT 1"},
                tool_output={"columns": ["?column?"], "rows": [[1]], "row_count": 1},
            )
        ]
        msg = _message("end_turn", content=[_text_block("The result is 1.")])
        result = agent._build_response(msg, tool_calls, total_tokens=200, elapsed=1500)

        assert result.status == "success"
        assert result.sql == "SELECT 1"
        assert result.results["row_count"] == 1
        assert result.explanation == "The result is 1."
        assert result.total_tokens == 200
        assert result.latency_ms == 1500

    def test_out_of_scope_response(self, agent):
        msg = _message("end_turn", content=[_text_block("Sorry, I can only help with Banking/POS data.")])
        result = agent._build_response(msg, [], total_tokens=100, elapsed=500)

        assert result.status == "out_of_scope"
        assert result.sql is None
        assert result.results is None

    def test_error_response_sql_but_no_results(self, agent):
        tool_calls = [
            ToolCallRecord(
                tool_name="execute_sql",
                tool_input={"sql": "SELECT * FROM bad"},
                tool_output={"error": "relation does not exist"},
            )
        ]
        msg = _message("end_turn", content=[_text_block("I couldn't run the query.")])
        result = agent._build_response(msg, tool_calls, total_tokens=150, elapsed=2000)

        assert result.status == "error"
        assert result.sql == "SELECT * FROM bad"
        assert result.results is None


# ---------------------------------------------------------------------------
# Tests — format_response_for_api
# ---------------------------------------------------------------------------

class TestFormatResponseForApi:
    def test_success_format(self):
        resp = AgentResponse(
            status="success",
            sql="SELECT 1",
            results={"columns": ["x"], "rows": [[1]], "row_count": 1},
            explanation="Result is 1",
            tool_calls=[ToolCallRecord(tool_name="execute_sql", tool_input={"sql": "SELECT 1"})],
            total_tokens=200,
            latency_ms=1500,
        )
        formatted = format_response_for_api(resp)
        assert formatted["status"] == "success"
        assert formatted["sql"] == "SELECT 1"
        assert formatted["results"]["row_count"] == 1
        assert formatted["metadata"]["latency_ms"] == 1500
        assert formatted["metadata"]["tool_calls"] == 1
        assert formatted["metadata"]["tokens"] == 200

    def test_out_of_scope_format(self):
        resp = AgentResponse(
            status="out_of_scope",
            explanation="Not a data question.",
            total_tokens=50,
            latency_ms=300,
        )
        formatted = format_response_for_api(resp)
        assert formatted["status"] == "out_of_scope"
        assert "sql" not in formatted
        assert "results" not in formatted
        assert formatted["explanation"] == "Not a data question."
