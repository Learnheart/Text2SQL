"""Tests for the Validator component — 6-step SQL validation."""

import pytest
from src.pipeline.validator import validate, _check_syntax, _check_dml, _extract_table_names, _ensure_limit


class TestSyntaxCheck:
    def test_valid_select(self):
        assert _check_syntax("SELECT * FROM sales") is True

    def test_valid_with_where(self):
        assert _check_syntax("SELECT id, total_amount FROM sales WHERE status = 'completed'") is True

    def test_empty_string(self):
        assert _check_syntax("") is False

    def test_none_like(self):
        assert _check_syntax("   ") is False


class TestDMLCheck:
    def test_select_allowed(self):
        assert _check_dml("SELECT * FROM sales") is None

    def test_with_cte_allowed(self):
        assert _check_dml("WITH cte AS (SELECT 1) SELECT * FROM cte") is None

    def test_insert_blocked(self):
        result = _check_dml("INSERT INTO sales VALUES (1)")
        assert result is not None
        assert "INSERT" in result

    def test_delete_blocked(self):
        result = _check_dml("DELETE FROM sales WHERE id = 1")
        assert result is not None
        assert "DELETE" in result

    def test_drop_blocked(self):
        result = _check_dml("DROP TABLE sales")
        assert result is not None
        assert "DROP" in result

    def test_update_blocked(self):
        result = _check_dml("UPDATE sales SET status = 'x'")
        assert result is not None
        assert "UPDATE" in result

    def test_truncate_blocked(self):
        result = _check_dml("TRUNCATE TABLE sales")
        assert result is not None
        assert "TRUNCATE" in result


class TestTableExtraction:
    def test_single_table(self):
        tables = _extract_table_names("SELECT * FROM sales")
        assert "sales" in tables

    def test_multiple_tables_join(self):
        sql = "SELECT s.id FROM sales s JOIN merchants m ON s.merchant_id = m.id"
        tables = _extract_table_names(sql)
        assert "sales" in tables
        assert "merchants" in tables

    def test_left_join(self):
        sql = "SELECT * FROM customers LEFT JOIN accounts ON customers.id = accounts.customer_id"
        tables = _extract_table_names(sql)
        assert "customers" in tables
        assert "accounts" in tables

    def test_subquery(self):
        sql = "SELECT * FROM sales WHERE merchant_id IN (SELECT id FROM merchants)"
        tables = _extract_table_names(sql)
        assert "sales" in tables
        assert "merchants" in tables


class TestLimitEnforcement:
    def test_adds_limit_when_missing(self):
        result = _ensure_limit("SELECT * FROM sales")
        assert "LIMIT 1000" in result

    def test_preserves_existing_limit(self):
        sql = "SELECT * FROM sales LIMIT 50"
        result = _ensure_limit(sql)
        assert result == sql

    def test_strips_semicolon_before_limit(self):
        result = _ensure_limit("SELECT * FROM sales;")
        assert "LIMIT 1000" in result
        assert not result.endswith(";LIMIT")


class TestValidateIntegration:
    def _make_state(self, sql: str) -> dict:
        return {"generated_sql": sql}

    def test_valid_select(self):
        state = validate(self._make_state("SELECT COUNT(*) FROM sales LIMIT 100"))
        assert state["validation_result"].is_valid is True
        assert len(state["validation_result"].errors) == 0

    def test_invalid_table(self):
        state = validate(self._make_state("SELECT * FROM nonexistent_table"))
        assert state["validation_result"].is_valid is False
        assert any("nonexistent_table" in e for e in state["validation_result"].errors)

    def test_dml_rejected(self):
        state = validate(self._make_state("DELETE FROM sales"))
        assert state["validation_result"].is_valid is False

    def test_auto_adds_limit(self):
        state = validate(self._make_state("SELECT * FROM sales"))
        assert "LIMIT 1000" in state["validation_result"].sanitized_sql

    def test_sensitive_column_warning(self):
        state = validate(self._make_state("SELECT cards.cvv FROM cards LIMIT 10"))
        assert len(state["validation_result"].warnings) > 0
        assert any("sensitive" in w.lower() for w in state["validation_result"].warnings)

    def test_empty_sql(self):
        state = validate(self._make_state(""))
        assert state["validation_result"].is_valid is False
