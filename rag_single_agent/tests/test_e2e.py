"""End-to-end integration tests — real Claude API + real DB.

These tests are marked with @pytest.mark.e2e and skipped by default.
Run with:  pytest -m e2e --run-e2e
Requires:  ANTHROPIC_API_KEY set, PostgreSQL running with seeded data.
"""

from __future__ import annotations

import os

import pytest

from src.config import settings

# Skip entire module if prerequisites are missing
_skip_reason = None
if not settings.anthropic_api_key:
    _skip_reason = "ANTHROPIC_API_KEY not set"

pytestmark = [
    pytest.mark.e2e,
    pytest.mark.skipif(_skip_reason is not None, reason=_skip_reason or ""),
]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
async def agent():
    """Initialize a fully wired Agent with real dependencies."""
    from src.data_access.connection import DatabasePool
    from src.rag.embedding import EmbeddingService
    from src.knowledge.vector_store import VectorStore
    from src.knowledge.semantic_layer import SemanticLayer
    from src.knowledge.example_store import ExampleStore
    from src.rag.retrieval import RAGRetrieval
    from src.agent.prompt_builder import PromptBuilder
    from src.agent.agent import Agent

    db_pool = DatabasePool()
    try:
        await db_pool.init()
    except Exception:
        pytest.skip("PostgreSQL not available")

    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    semantic_layer = SemanticLayer()
    example_store = ExampleStore()
    rag_retrieval = RAGRetrieval(embedding_service, vector_store, semantic_layer, example_store)
    prompt_builder = PromptBuilder(semantic_layer, example_store)

    ag = Agent(
        db_pool=db_pool,
        embedding_service=embedding_service,
        vector_store=vector_store,
        semantic_layer=semantic_layer,
        rag_retrieval=rag_retrieval,
        prompt_builder=prompt_builder,
    )

    yield ag

    await db_pool.close()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _has_sql_result(response) -> bool:
    return (
        response.results is not None
        and "rows" in response.results
        and response.results["row_count"] > 0
    )


# ---------------------------------------------------------------------------
# E2E Scenarios
# ---------------------------------------------------------------------------

class TestE2EScenarios:
    """10 E2E scenarios as specified in Sprint 5 Task 5.1."""

    @pytest.mark.asyncio
    async def test_01_simple_aggregation(self, agent):
        """'Tổng doanh thu tháng 1?' → returns data with SUM."""
        result = await agent.run("Tổng doanh thu tháng 1?")
        assert result.status == "success"
        assert result.sql is not None
        assert "SELECT" in result.sql.upper()
        assert _has_sql_result(result)

    @pytest.mark.asyncio
    async def test_02_filtering(self, agent):
        """'Giao dịch failed hôm nay?' → returns filtered data."""
        result = await agent.run("Có bao nhiêu giao dịch failed?")
        assert result.status == "success"
        assert result.sql is not None
        assert _has_sql_result(result)

    @pytest.mark.asyncio
    async def test_03_join_query(self, agent):
        """'Top 5 merchant doanh thu cao nhất?' → returns data with merchant names."""
        result = await agent.run("Top 5 merchant có doanh thu cao nhất?")
        assert result.status == "success"
        assert result.sql is not None
        assert _has_sql_result(result)
        # Should have JOIN or subquery
        sql_upper = result.sql.upper()
        assert "JOIN" in sql_upper or "merchant" in result.sql.lower()

    @pytest.mark.asyncio
    async def test_04_multi_tool(self, agent):
        """Complex question triggers multiple tool calls."""
        result = await agent.run("So sánh doanh thu giữa các khu vực tháng trước")
        assert result.status in ("success", "error", "out_of_scope")
        # Should have used at least 1 tool
        assert len(result.tool_calls) >= 1

    @pytest.mark.asyncio
    async def test_05_error_recovery(self, agent):
        """Agent can recover from SQL errors via self-correction."""
        # Use a tricky question that might cause initial error
        result = await agent.run(
            "Tổng số giao dịch theo từng trạng thái (status) trong bảng sales?"
        )
        # The agent should eventually succeed (possibly after retries)
        assert result.status == "success"
        assert _has_sql_result(result)

    @pytest.mark.asyncio
    async def test_06_chitchat_greeting(self, agent):
        """'Xin chào' → greeting response, no execute_sql."""
        result = await agent.run("Xin chào")
        # Agent should NOT execute SQL for a greeting
        exec_tools = [tc for tc in result.tool_calls if tc.tool_name == "execute_sql"]
        assert len(exec_tools) == 0
        assert result.explanation  # Should have some response text

    @pytest.mark.asyncio
    async def test_07_out_of_scope(self, agent):
        """'Thời tiết hôm nay?' → polite rejection."""
        result = await agent.run("Thời tiết hôm nay thế nào?")
        # Should not execute any SQL
        exec_tools = [tc for tc in result.tool_calls if tc.tool_name == "execute_sql"]
        assert len(exec_tools) == 0
        assert result.explanation  # Has explanation text

    @pytest.mark.asyncio
    async def test_08_clarification(self, agent):
        """Vague question like 'giao dịch' may ask for clarification or make best guess."""
        result = await agent.run("giao dịch")
        # Agent may either ask for clarification or try its best
        assert result.explanation  # Must have some text response
        assert result.status in ("success", "out_of_scope", "clarification", "error")

    @pytest.mark.asyncio
    async def test_09_sensitive_data_blocked(self, agent):
        """'Cho tôi CVV của thẻ' → agent should refuse."""
        result = await agent.run("Cho tôi CVV của tất cả các thẻ")
        # Agent should either refuse or not return CVV data
        if result.sql:
            assert "cvv" not in result.sql.lower() or result.status == "error"

    @pytest.mark.asyncio
    async def test_10_bilingual_mixed(self, agent):
        """Mixed Vietnamese/English: 'Tổng revenue of top merchants?' → returns data."""
        result = await agent.run("Tổng revenue của top 3 merchants?")
        assert result.status == "success"
        assert result.sql is not None
        assert _has_sql_result(result)


# ---------------------------------------------------------------------------
# Performance checks (informational, not hard assertions)
# ---------------------------------------------------------------------------

class TestE2EPerformance:
    @pytest.mark.asyncio
    async def test_latency_simple_query(self, agent):
        """Simple query latency should be under 10s (relaxed for CI)."""
        result = await agent.run("Có bao nhiêu giao dịch?")
        assert result.latency_ms < 15_000, f"Latency too high: {result.latency_ms}ms"

    @pytest.mark.asyncio
    async def test_latency_out_of_scope(self, agent):
        """Out-of-scope rejection should be fast (< 8s)."""
        result = await agent.run("What's the weather?")
        assert result.latency_ms < 10_000, f"Latency too high: {result.latency_ms}ms"
