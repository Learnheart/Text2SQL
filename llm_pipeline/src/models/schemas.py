"""Pydantic models for the LLM-in-the-middle pipeline."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# --- Enums ---


class IntentType(str, Enum):
    """Router intent classification result."""

    SQL = "sql"
    CHITCHAT = "chitchat"
    CLARIFICATION = "clarification"
    OUT_OF_SCOPE = "out_of_scope"


class PipelineStatus(str, Enum):
    """Overall pipeline execution status."""

    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    EXECUTION_ERROR = "execution_error"
    MAX_RETRIES = "max_retries"
    REJECTED = "rejected"
    CLARIFICATION = "clarification"
    ERROR = "error"


# --- Knowledge Layer models ---


class MetricDef(BaseModel):
    """Definition of a business metric from the semantic layer."""

    name: str
    sql: str
    filter: str = ""
    aliases: list[str] = Field(default_factory=list)
    description: str = ""


class Example(BaseModel):
    """A golden query example (question -> SQL pair)."""

    question: str
    sql: str
    explanation: str = ""


# --- Router models ---


class RouterResult(BaseModel):
    """Output from the Router component."""

    intent: IntentType
    confidence: float = 1.0
    message: str = ""  # Default response for non-SQL intents


# --- Schema Linker models ---


class ContextPackage(BaseModel):
    """Context assembled by Schema Linker for SQL Generator."""

    schema_chunks: list[str] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    metrics: list[MetricDef] = Field(default_factory=list)
    join_hints: list[str] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    sensitive_columns: list[str] = Field(default_factory=list)


# --- Validator models ---


class ValidationResult(BaseModel):
    """Output from the Validator component."""

    is_valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    sanitized_sql: str = ""


# --- Executor models ---


class ExecutionResult(BaseModel):
    """Output from the Executor component."""

    columns: list[str] = Field(default_factory=list)
    rows: list[list[Any]] = Field(default_factory=list)
    row_count: int = 0
    execution_time_ms: int = 0
    error: str | None = None


# --- Pipeline Response ---


class PipelineResponse(BaseModel):
    """Final response from the pipeline."""

    status: PipelineStatus
    sql: str | None = None
    results: ExecutionResult | None = None
    explanation: str = ""
    intent: IntentType = IntentType.SQL
    attempts: int = 0
    total_tokens: int = 0
    latency_ms: int = 0


# --- Audit ---


class AuditRecord(BaseModel):
    """Audit log entry for compliance (Banking domain requirement)."""

    question: str
    generated_sql: str | None = None
    row_count: int | None = None
    status: str = "pending"
    error_message: str | None = None
    latency_ms: int = 0
    attempts: int = 0
    tokens_used: int = 0
    model_used: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


# --- API models ---


class QueryRequest(BaseModel):
    """Request body for POST /api/query."""

    question: str
    session_id: str | None = None


class QueryResponse(BaseModel):
    """Response body for POST /api/query."""

    status: str
    sql: str | None = None
    results: dict[str, Any] | None = None
    explanation: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackRequest(BaseModel):
    """Request body for POST /api/feedback."""

    question: str
    wrong_sql: str | None = None
    correct_sql: str
