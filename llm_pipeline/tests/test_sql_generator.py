"""Tests for the SQL Generator component."""

import pytest
from unittest.mock import MagicMock

from src.llm.base import LLMResponse
from src.models.schemas import ContextPackage, Example, MetricDef
from src.pipeline.sql_generator import generate_sql, _extract_sql, _build_user_message


class TestSQLExtraction:
    def test_extract_from_code_block(self):
        text = "Here is the query:\n```sql\nSELECT COUNT(*) FROM sales\n```"
        assert _extract_sql(text) == "SELECT COUNT(*) FROM sales"

    def test_extract_from_bare_code_block(self):
        text = "```\nSELECT * FROM merchants\n```"
        assert _extract_sql(text) == "SELECT * FROM merchants"

    def test_extract_raw_select(self):
        text = "SELECT SUM(total_amount) FROM sales WHERE status = 'completed'"
        result = _extract_sql(text)
        assert result is not None
        assert "SELECT" in result

    def test_extract_with_cte(self):
        text = "```sql\nWITH cte AS (SELECT 1) SELECT * FROM cte\n```"
        result = _extract_sql(text)
        assert result is not None
        assert "WITH" in result

    def test_extract_returns_none_for_nonsql(self):
        text = "I cannot generate SQL for that question."
        assert _extract_sql(text) is None


class TestUserMessage:
    def test_normal_question(self):
        msg = _build_user_message("Tổng doanh thu?", "")
        assert "Tổng doanh thu?" in msg
        assert "PREVIOUS ATTEMPT" not in msg

    def test_retry_with_feedback(self):
        msg = _build_user_message("Tổng doanh thu?", "Table 'transaction' not found")
        assert "PREVIOUS ATTEMPT FAILED" in msg
        assert "transaction" in msg
        assert "Tổng doanh thu?" in msg


class TestGenerateSQL:
    def test_generate_returns_sql(self):
        """Test that generate_sql calls LLM and extracts SQL."""
        mock_provider = MagicMock()
        mock_provider.create.return_value = LLMResponse(
            text="```sql\nSELECT COUNT(*) FROM sales\n```",
            input_tokens=100,
            output_tokens=20,
        )

        state = {
            "question": "Bao nhiêu giao dịch?",
            "context_package": ContextPackage(
                schema_chunks=["Table: sales\n  Columns: id, total_amount, status"],
                examples=[Example(question="Count sales", sql="SELECT COUNT(*) FROM sales")],
                metrics=[],
                join_hints=[],
                business_rules=["Revenue only counts completed sales"],
                sensitive_columns=["cards.cvv"],
            ),
            "attempt": 1,
            "error_feedback": "",
            "total_tokens": 0,
        }

        result = generate_sql(state, llm_provider=mock_provider)

        assert result["generated_sql"] == "SELECT COUNT(*) FROM sales"
        assert result["generation_tokens"] == 120
        assert mock_provider.create.called

    def test_generate_increments_tokens(self):
        """Test that total_tokens accumulates across retries."""
        mock_provider = MagicMock()
        mock_provider.create.return_value = LLMResponse(
            text="```sql\nSELECT 1\n```",
            input_tokens=50,
            output_tokens=10,
        )

        state = {
            "question": "Test",
            "context_package": ContextPackage(),
            "attempt": 2,
            "error_feedback": "Previous error",
            "total_tokens": 100,
        }

        result = generate_sql(state, llm_provider=mock_provider)

        assert result["total_tokens"] == 160  # 100 + 60
