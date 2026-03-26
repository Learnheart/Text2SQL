"""Self-Correction Loop [CODE] — Handles retry logic when Validator/Executor fails.

Logic:
- If validation fails or execution fails, increment attempt counter
- If attempt < max_retries: feed error back to SQL Generator for retry
- If attempt >= max_retries: return error to user
- Error feedback includes specific hints based on error type

This is pure conditional logic — no LLM is used.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from src.config import settings
from src.models.schemas import PipelineStatus
from src.pipeline.state import PipelineState

if TYPE_CHECKING:
    from src.session_logger import SessionLogger


def should_retry(state: PipelineState) -> str:
    """LangGraph conditional edge: decide whether to retry or finish.

    Returns:
        "retry" — go back to SQL Generator with error feedback
        "success" — execution succeeded, proceed to response
        "max_retries" — exhausted retries, return error
    """
    # Check if execution succeeded
    execution_result = state.get("execution_result")
    if execution_result and not execution_result.error:
        return "success"

    # Check if validation failed
    validation_result = state.get("validation_result")
    if validation_result and not validation_result.is_valid:
        attempt = state.get("attempt", 1)
        if attempt < settings.pipeline_max_retries:
            return "retry"
        return "max_retries"

    # Check if execution failed
    if execution_result and execution_result.error:
        attempt = state.get("attempt", 1)
        if attempt < settings.pipeline_max_retries:
            return "retry"
        return "max_retries"

    return "success"


def prepare_retry(state: PipelineState, *, session_log: SessionLogger | None = None) -> PipelineState:
    """Prepare state for retry: increment attempt, build error feedback.

    Called when should_retry returns "retry".
    """
    attempt = state.get("attempt", 1) + 1
    error_history = list(state.get("error_history", []))

    # Collect error information
    error_info: dict = {"attempt": attempt - 1}

    validation_result = state.get("validation_result")
    execution_result = state.get("execution_result")

    if validation_result and not validation_result.is_valid:
        error_info["type"] = "validation"
        error_info["errors"] = validation_result.errors
        error_feedback = _build_validation_feedback(state)
    elif execution_result and execution_result.error:
        error_info["type"] = "execution"
        error_info["error"] = execution_result.error
        error_feedback = state.get("error_feedback", execution_result.error)
    else:
        error_feedback = "Unknown error occurred."

    error_info["sql"] = state.get("generated_sql", "")
    error_history.append(error_info)

    if session_log:
        session_log.info(
            "SELF_CORRECTION",
            f"Retry {attempt}/{settings.pipeline_max_retries}: {error_info.get('type', 'unknown')} error",
        )

    return {
        **state,
        "attempt": attempt,
        "error_feedback": error_feedback,
        "error_history": error_history,
        # Clear previous results for fresh attempt
        "generated_sql": "",
        "validation_result": None,
        "execution_result": None,
    }


def finalize_max_retries(state: PipelineState, *, session_log: SessionLogger | None = None) -> PipelineState:
    """Finalize state when max retries exhausted."""
    if session_log:
        session_log.error(
            "SELF_CORRECTION",
            f"Max retries ({settings.pipeline_max_retries}) exhausted. Returning error to user.",
        )

    return {
        **state,
        "status": PipelineStatus.MAX_RETRIES,
        "explanation": (
            f"Không thể tạo SQL chính xác sau {settings.pipeline_max_retries} lần thử. "
            f"Vui lòng thử diễn đạt câu hỏi khác hoặc cụ thể hơn."
        ),
    }


def _build_validation_feedback(state: PipelineState) -> str:
    """Build structured feedback from validation errors for SQL Generator."""
    validation = state.get("validation_result")
    if not validation:
        return "Validation failed with unknown error."

    sql = state.get("generated_sql", "")
    parts = [
        f"The SQL query failed validation with the following errors:",
    ]

    for error in validation.errors:
        parts.append(f"- {error}")

    parts.append(f"\nFailed SQL: {sql}")
    parts.append("\nPlease generate a corrected SQL query that fixes these issues.")

    return "\n".join(parts)
