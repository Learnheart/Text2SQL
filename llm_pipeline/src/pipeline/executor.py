"""Executor [CODE] — Runs validated SQL on PostgreSQL with safety enforcement.

Features:
- Read-only connection (enforced by DatabasePool)
- Statement timeout: 30 seconds
- Auto LIMIT enforcement
- Audit logging for Banking compliance
- Error categorization for self-correction feedback

No LLM is used — purely executes SQL on the database.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.data_access.connection import DatabasePool
from src.models.schemas import ExecutionResult
from src.pipeline.state import PipelineState

if TYPE_CHECKING:
    from src.session_logger import SessionLogger


async def execute(
    state: PipelineState,
    *,
    db_pool: DatabasePool,
    session_log: SessionLogger | None = None,
) -> PipelineState:
    """Execute validated SQL and return results.

    Uses the sanitized SQL from the Validator (which has LIMIT enforced).
    Processing time target: ~200ms.
    """
    validation = state.get("validation_result")
    if not validation or not validation.is_valid:
        return {
            **state,
            "execution_result": ExecutionResult(error="Cannot execute: SQL validation failed"),
        }

    sql = validation.sanitized_sql
    if not sql:
        return {
            **state,
            "execution_result": ExecutionResult(error="No SQL to execute"),
        }

    if session_log:
        session_log.step(6, "EXECUTOR", f"Executing SQL: {sql[:100]}")

    result = await db_pool.execute(sql)

    if "error" in result:
        error_msg = result["error"]
        if session_log:
            session_log.detail("EXECUTOR", f"FAIL: {error_msg}")

        # Categorize error for self-correction feedback
        feedback = _build_error_feedback(sql, error_msg)

        return {
            **state,
            "execution_result": ExecutionResult(error=error_msg),
            "error_feedback": feedback,
        }

    execution_result = ExecutionResult(
        columns=result.get("columns", []),
        rows=result.get("rows", []),
        row_count=result.get("row_count", 0),
        execution_time_ms=result.get("execution_time_ms", 0),
    )

    if session_log:
        session_log.detail(
            "EXECUTOR",
            f"SUCCESS: {execution_result.row_count} rows in {execution_result.execution_time_ms}ms",
        )

    return {
        **state,
        "execution_result": execution_result,
        "status": "success",
    }


def _build_error_feedback(sql: str, error: str) -> str:
    """Build structured error feedback for the SQL Generator to retry.

    Provides specific guidance based on the error type.
    """
    feedback_parts = [
        f"The SQL query failed with error: {error}",
        f"Failed SQL: {sql}",
    ]

    error_lower = error.lower()

    if "does not exist" in error_lower:
        if "column" in error_lower:
            feedback_parts.append(
                "HINT: A column name is incorrect. Check the exact column names in the schema context provided."
            )
        elif "relation" in error_lower or "table" in error_lower:
            feedback_parts.append(
                "HINT: A table name is incorrect. Use only tables from the schema context."
            )

    elif "permission denied" in error_lower:
        feedback_parts.append("HINT: This is a read-only connection. Only SELECT queries are allowed.")

    elif "timed out" in error_lower or "timeout" in error_lower:
        feedback_parts.append(
            "HINT: The query took too long. Simplify it — reduce JOINs, add WHERE filters, or use LIMIT."
        )

    elif "syntax" in error_lower:
        feedback_parts.append(
            "HINT: There is a SQL syntax error. Use valid PostgreSQL syntax."
        )

    elif "type" in error_lower and ("mismatch" in error_lower or "cast" in error_lower):
        feedback_parts.append(
            "HINT: There is a type mismatch. Check column types and use explicit casts (::date, ::numeric, etc.)."
        )

    feedback_parts.append("Please generate a corrected SQL query.")
    return "\n".join(feedback_parts)
