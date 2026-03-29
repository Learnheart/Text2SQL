"""Tests for Agent core: tool use loop, dispatch, response building."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.models.schemas import AgentResponse, RAGContext, MetricDef, Example, ToolCallRecord
from src.agent.agent import Agent
from src.agent.response_parser import format_response_for_api
from src.llm.base import LLMResponse, ToolCall


# ---------------------------------------------------------------------------
# Helpers to build mock LLM responses
# ---------------------------------------------------------------------------

def _llm_text(text: str, tokens: int = 150) -> LLMResponse:
    """Create an LLMResponse with text only (end_turn)."""
    return LLMResponse(
        text=text,
        tool_calls=[],
        stop_reason="end_turn",
        input_tokens=tokens // 2,
        output_tokens=tokens // 2,
    )


def _llm_tool_use(tool_calls: list[ToolCall], text: str | None = None, tokens: int = 150) -> LLMResponse:
    """Create an LLMResponse with tool calls."""
    return LLMResponse(
        text=text,
        tool_calls=tool_calls,
        stop_reason="tool_use",
        input_tokens=tokens // 2,
        output_tokens=tokens // 2,
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

    llm_provider = MagicMock()
    # Default: format_tool_result returns Anthropic-style dict
    llm_provider.format_tool_result.side_effect = lambda **kw: {
        "type": "tool_result",
        "tool_use_id": kw["tool_call_id"],
        "content": kw["content"],
    }
    llm_provider.format_assistant_message.return_value = {"role": "assistant", "content": "..."}

    return {
        "db_pool": db_pool,
        "embedding_service": embedding_service,
        "vector_store": vector_store,
        "semantic_layer": semantic_layer,
        "rag_retrieval": rag_retrieval,
        "prompt_builder": prompt_builder,
        "llm_provider": llm_provider,
    }


@pytest.fixture
def agent(mock_deps):
    """Create Agent with mocked deps and mocked LLM provider."""
    return Agent(**mock_deps)


# ---------------------------------------------------------------------------
# Tests — Happy path
# ---------------------------------------------------------------------------

class TestAgentHappyPath:
    @pytest.mark.asyncio
    async def test_single_tool_call_success(self, agent):
        """Question → execute_sql tool call → final response with results."""
        tool_call_resp = _llm_tool_use([
            ToolCall(id="tc_1", name="execute_sql", input={"sql": "SELECT SUM(total_amount) FROM sales"}),
        ], text="Let me query the database.")
        final_resp = _llm_text("Total revenue is 1,000,000 VND.")

        agent._llm.create = MagicMock(side_effect=[tool_call_resp, final_resp])

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
        resp1 = _llm_tool_use([ToolCall(id="tc_1", name="search_schema", input={"query": "merchant tables"})])
        resp2 = _llm_tool_use([ToolCall(id="tc_2", name="get_metric_definition", input={"metric_name": "doanh_thu"})])
        resp3 = _llm_tool_use([ToolCall(id="tc_3", name="execute_sql", input={"sql": "SELECT SUM(total_amount) FROM sales"})])
        resp4 = _llm_text("Here are the results.")

        agent._llm.create = MagicMock(side_effect=[resp1, resp2, resp3, resp4])

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
        final = _llm_text("Xin lỗi, tôi chỉ hỗ trợ câu hỏi về dữ liệu Banking/POS.")
        agent._llm.create = MagicMock(return_value=final)

        result = await agent.run("Thời tiết hôm nay thế nào?")

        assert result.status == "out_of_scope"
        assert result.sql is None
        assert result.results is None
        assert len(result.tool_calls) == 0
        assert "Banking/POS" in result.explanation or "xin lỗi" in result.explanation.lower()

    @pytest.mark.asyncio
    async def test_greeting(self, agent):
        """Greeting → friendly response, no tools."""
        final = _llm_text("Xin chào! Tôi có thể giúp bạn truy vấn dữ liệu Banking/POS.")
        agent._llm.create = MagicMock(return_value=final)

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
        resp1 = _llm_tool_use([
            ToolCall(id="tc_1", name="execute_sql", input={"sql": "SELECT * FROM nonexistent_table"}),
        ])
        resp2 = _llm_tool_use([
            ToolCall(id="tc_2", name="execute_sql", input={"sql": "SELECT * FROM sales LIMIT 10"}),
        ], text="The table doesn't exist. Let me use the correct table name.")
        resp3 = _llm_text("Here are the sales records.")

        agent._llm.create = MagicMock(side_effect=[resp1, resp2, resp3])

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

class TestAgentDedupGuard:
    @pytest.mark.asyncio
    async def test_dedup_breaks_on_identical_tool_calls(self, agent):
        """Agent calls execute_sql with same input twice → dedup guard breaks loop."""
        same_sql = "SELECT SUM(total_amount) FROM sales"
        resp_tool = _llm_tool_use([
            ToolCall(id="tc_1", name="execute_sql", input={"sql": same_sql}),
        ])
        # Model keeps returning the same tool call every iteration
        agent._llm.create = MagicMock(return_value=resp_tool)

        with patch("src.agent.agent.execute_sql", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = {"columns": ["sum"], "rows": [[1000000]], "row_count": 1}
            result = await agent.run("Tổng doanh thu?")

        # Should only execute once — dedup guard stops at iteration 2
        assert mock_exec.call_count == 1
        assert result.status == "success"
        assert result.sql == same_sql
        assert result.results["row_count"] == 1

    @pytest.mark.asyncio
    async def test_dedup_allows_different_inputs(self, agent):
        """Same tool with different inputs should NOT be blocked by dedup."""
        resp1 = _llm_tool_use([
            ToolCall(id="tc_1", name="execute_sql", input={"sql": "SELECT * FROM bad_table"}),
        ])
        resp2 = _llm_tool_use([
            ToolCall(id="tc_2", name="execute_sql", input={"sql": "SELECT * FROM sales LIMIT 10"}),
        ])
        resp3 = _llm_text("Here are the results.")

        agent._llm.create = MagicMock(side_effect=[resp1, resp2, resp3])

        call_count = 0

        async def mock_exec(sql, pool):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return {"error": 'relation "bad_table" does not exist'}
            return {"columns": ["id"], "rows": [[1]], "row_count": 1}

        with patch("src.agent.agent.execute_sql", side_effect=mock_exec):
            result = await agent.run("Show sales")

        assert result.status == "success"
        assert len(result.tool_calls) == 2


class TestAgentMaxToolCalls:
    @pytest.mark.asyncio
    async def test_max_tool_calls_reached(self, agent):
        """Agent keeps calling tools with different inputs until hitting the limit."""
        call_idx = 0

        def make_response(*args, **kwargs):
            nonlocal call_idx
            call_idx += 1
            return _llm_tool_use([
                ToolCall(id=f"tc_{call_idx}", name="search_schema", input={"query": f"something_{call_idx}"}),
            ])

        agent._llm.create = MagicMock(side_effect=make_response)

        with patch("src.agent.agent.search_schema", new_callable=AsyncMock) as mock_search:
            mock_search.return_value = {"results": []}
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
    def test_success_response(self):
        tool_calls = [
            ToolCallRecord(
                tool_name="execute_sql",
                tool_input={"sql": "SELECT 1"},
                tool_output={"columns": ["?column?"], "rows": [[1]], "row_count": 1},
            )
        ]
        llm_resp = _llm_text("The result is 1.")
        result = Agent._build_response(llm_resp, tool_calls, total_tokens=200, elapsed=1500)

        assert result.status == "success"
        assert result.sql == "SELECT 1"
        assert result.results["row_count"] == 1
        assert result.explanation == "The result is 1."
        assert result.total_tokens == 200
        assert result.latency_ms == 1500

    def test_out_of_scope_response(self):
        llm_resp = _llm_text("Sorry, I can only help with Banking/POS data.")
        result = Agent._build_response(llm_resp, [], total_tokens=100, elapsed=500)

        assert result.status == "out_of_scope"
        assert result.sql is None
        assert result.results is None

    def test_error_response_sql_but_no_results(self):
        tool_calls = [
            ToolCallRecord(
                tool_name="execute_sql",
                tool_input={"sql": "SELECT * FROM bad"},
                tool_output={"error": "relation does not exist"},
            )
        ]
        llm_resp = _llm_text("I couldn't run the query.")
        result = Agent._build_response(llm_resp, tool_calls, total_tokens=150, elapsed=2000)

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
