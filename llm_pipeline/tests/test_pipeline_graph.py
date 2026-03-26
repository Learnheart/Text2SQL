"""Tests for the LangGraph pipeline orchestration — unit tests using mocks."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.models.schemas import (
    ContextPackage,
    ExecutionResult,
    IntentType,
    PipelineStatus,
    RouterResult,
    ValidationResult,
)
from src.pipeline.state import PipelineState


class TestRouterRouting:
    """Test that router correctly routes different intents."""

    def test_sql_intent_proceeds(self):
        from src.pipeline.router import route
        state = route({"question": "Tổng doanh thu tháng 3?"})
        assert state["router_result"].intent == IntentType.SQL

    def test_chitchat_rejected(self):
        from src.pipeline.router import route
        state = route({"question": "Xin chào"})
        assert state["router_result"].intent == IntentType.CHITCHAT

    def test_out_of_scope_rejected(self):
        from src.pipeline.router import route
        state = route({"question": "How to cook rice?"})
        assert state["router_result"].intent == IntentType.OUT_OF_SCOPE


class TestPipelineFlow:
    """Test the logical flow of the pipeline using component functions."""

    def test_validation_blocks_bad_sql(self):
        """Validator should catch invalid table names."""
        from src.pipeline.validator import validate
        state = validate({"generated_sql": "SELECT * FROM nonexistent"})
        assert state["validation_result"].is_valid is False

    def test_validation_passes_good_sql(self):
        """Validator should pass valid SQL referencing real tables."""
        from src.pipeline.validator import validate
        state = validate({"generated_sql": "SELECT COUNT(*) FROM sales LIMIT 10"})
        assert state["validation_result"].is_valid is True

    def test_retry_logic_increments(self):
        """Self-correction should increment attempt counter."""
        from src.pipeline.self_correction import prepare_retry
        state = prepare_retry({
            "attempt": 1,
            "error_history": [],
            "validation_result": ValidationResult(is_valid=False, errors=["error"]),
            "generated_sql": "SELECT bad",
        })
        assert state["attempt"] == 2

    def test_max_retries_stops_pipeline(self):
        """After max retries, pipeline should stop with MAX_RETRIES status."""
        from src.pipeline.self_correction import finalize_max_retries
        state = finalize_max_retries({"attempt": 3})
        assert state["status"] == PipelineStatus.MAX_RETRIES


class TestEndToEndMocked:
    """Test full pipeline with mocked LLM and DB."""

    @pytest.mark.asyncio
    async def test_happy_path(self):
        """Test successful pipeline execution with mocks."""
        from src.pipeline.router import route
        from src.pipeline.validator import validate

        # 1. Router → SQL
        state: dict = {"question": "Tổng doanh thu?", "attempt": 1, "total_tokens": 0}
        state = route(state)
        assert state["router_result"].intent == IntentType.SQL

        # 2. Mock Schema Linker output
        state["context_package"] = ContextPackage(
            schema_chunks=["Table: sales\n  Columns: id, total_amount"],
        )

        # 3. Mock SQL Generator output
        state["generated_sql"] = "SELECT SUM(total_amount) FROM sales WHERE status = 'completed' LIMIT 100"
        state["generation_tokens"] = 50
        state["total_tokens"] = 50

        # 4. Validator
        state = validate(state)
        assert state["validation_result"].is_valid is True

        # 5. Mock Executor output
        state["execution_result"] = ExecutionResult(
            columns=["sum"],
            rows=[[1500000]],
            row_count=1,
            execution_time_ms=50,
        )
        state["status"] = PipelineStatus.SUCCESS

        assert state["execution_result"].row_count == 1
        assert state["execution_result"].error is None
