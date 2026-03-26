"""LangGraph state definition for the LLM-in-the-middle pipeline.

The state flows through: Router -> Schema Linker -> SQL Generator -> Validator -> Executor
with self-correction loops on validation/execution errors.
"""

from __future__ import annotations

from typing import Any, TypedDict

from src.models.schemas import (
    ContextPackage,
    ExecutionResult,
    IntentType,
    PipelineStatus,
    RouterResult,
    ValidationResult,
)


class PipelineState(TypedDict, total=False):
    """Typed state that flows through the LangGraph pipeline.

    Each node reads/writes specific keys. LangGraph manages the state
    and passes it between nodes via conditional edges.
    """

    # --- Input ---
    question: str
    session_id: str

    # --- Router output ---
    router_result: RouterResult

    # --- Schema Linker output ---
    context_package: ContextPackage

    # --- SQL Generator output ---
    generated_sql: str
    generation_model: str  # Which model was used (sonnet/opus)
    generation_tokens: int

    # --- Validator output ---
    validation_result: ValidationResult

    # --- Executor output ---
    execution_result: ExecutionResult

    # --- Self-correction state ---
    attempt: int  # Current attempt number (1-based)
    error_feedback: str  # Error message fed back to SQL Generator on retry
    error_history: list[dict[str, Any]]  # History of errors for debugging

    # --- Final output ---
    status: PipelineStatus
    explanation: str
    total_tokens: int
    latency_ms: int
