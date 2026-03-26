"""Tests for the Self-Correction Loop component."""

import pytest
from src.models.schemas import ExecutionResult, PipelineStatus, ValidationResult
from src.pipeline.self_correction import should_retry, prepare_retry, finalize_max_retries


class TestShouldRetry:
    def test_success_when_execution_ok(self):
        state = {
            "execution_result": ExecutionResult(columns=["id"], rows=[[1]], row_count=1),
            "attempt": 1,
        }
        assert should_retry(state) == "success"

    def test_retry_on_validation_error(self):
        state = {
            "validation_result": ValidationResult(is_valid=False, errors=["Table not found"]),
            "attempt": 1,
        }
        assert should_retry(state) == "retry"

    def test_retry_on_execution_error(self):
        state = {
            "execution_result": ExecutionResult(error="column x does not exist"),
            "attempt": 1,
        }
        assert should_retry(state) == "retry"

    def test_max_retries_on_validation_error(self):
        state = {
            "validation_result": ValidationResult(is_valid=False, errors=["Error"]),
            "attempt": 3,
        }
        assert should_retry(state) == "max_retries"

    def test_max_retries_on_execution_error(self):
        state = {
            "execution_result": ExecutionResult(error="timeout"),
            "attempt": 3,
        }
        assert should_retry(state) == "max_retries"


class TestPrepareRetry:
    def test_increments_attempt(self):
        state = {
            "attempt": 1,
            "error_history": [],
            "validation_result": ValidationResult(is_valid=False, errors=["Table not found"]),
            "generated_sql": "SELECT * FROM bad_table",
        }
        result = prepare_retry(state)
        assert result["attempt"] == 2

    def test_clears_previous_results(self):
        state = {
            "attempt": 1,
            "error_history": [],
            "execution_result": ExecutionResult(error="column not found"),
            "generated_sql": "SELECT bad FROM sales",
        }
        result = prepare_retry(state)
        assert result["generated_sql"] == ""
        assert result["validation_result"] is None
        assert result["execution_result"] is None

    def test_builds_error_feedback(self):
        state = {
            "attempt": 1,
            "error_history": [],
            "validation_result": ValidationResult(is_valid=False, errors=["Table 'tx' does not exist"]),
            "generated_sql": "SELECT * FROM tx",
        }
        result = prepare_retry(state)
        assert "error" in result["error_feedback"].lower() or "fail" in result["error_feedback"].lower()

    def test_appends_to_error_history(self):
        state = {
            "attempt": 2,
            "error_history": [{"attempt": 1, "type": "validation"}],
            "validation_result": ValidationResult(is_valid=False, errors=["Column not found"]),
            "generated_sql": "SELECT bad FROM sales",
        }
        result = prepare_retry(state)
        assert len(result["error_history"]) == 2


class TestFinalizeMaxRetries:
    def test_sets_max_retries_status(self):
        state = {"attempt": 3}
        result = finalize_max_retries(state)
        assert result["status"] == PipelineStatus.MAX_RETRIES

    def test_has_explanation(self):
        state = {"attempt": 3}
        result = finalize_max_retries(state)
        assert result["explanation"] != ""
