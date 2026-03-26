"""Tests for tools: execute_sql safety checks, get_metric, search_schema."""

import pytest

from src.tools.execute_sql import _add_limit
from src.tools.get_metric import get_metric_definition
from src.tools.search_schema import TOOL_DEFINITION as SEARCH_DEF
from src.tools.get_column_values import TOOL_DEFINITION as COL_DEF
from src.knowledge.semantic_layer import SemanticLayer


class TestExecuteSqlSafety:
    def test_add_limit_when_missing(self):
        sql = "SELECT * FROM sales"
        result = _add_limit(sql)
        assert "LIMIT 1000" in result

    def test_add_limit_preserves_existing(self):
        sql = "SELECT * FROM sales LIMIT 10"
        result = _add_limit(sql)
        assert result.count("LIMIT") == 1

    def test_add_limit_case_insensitive(self):
        sql = "SELECT * FROM sales limit 5"
        result = _add_limit(sql)
        assert result.count("limit") == 1  # not doubled


class TestGetMetricDefinition:
    @pytest.fixture
    def sl(self):
        return SemanticLayer()

    @pytest.mark.asyncio
    async def test_found(self, sl):
        result = await get_metric_definition("doanh thu", sl)
        assert "sql" in result
        assert "SUM" in result["sql"]

    @pytest.mark.asyncio
    async def test_not_found(self, sl):
        result = await get_metric_definition("nonexistent", sl)
        assert "error" in result
        assert "available_metrics" in result


class TestToolDefinitions:
    def test_search_schema_definition(self):
        assert SEARCH_DEF["name"] == "search_schema"
        assert "query" in SEARCH_DEF["input_schema"]["properties"]

    def test_get_column_values_definition(self):
        assert COL_DEF["name"] == "get_column_values"
        assert "table" in COL_DEF["input_schema"]["properties"]
        assert "column" in COL_DEF["input_schema"]["properties"]
