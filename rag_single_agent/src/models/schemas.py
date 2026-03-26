from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# --- Knowledge Layer models ---


class MetricDef(BaseModel):
    """Definition of a business metric from the semantic layer."""

    name: str
    sql: str
    filter: str = ""
    aliases: list[str] = Field(default_factory=list)
    description: str = ""


class Example(BaseModel):
    """A golden query example (question → SQL pair)."""

    question: str
    sql: str
    explanation: str = ""


# --- RAG models ---


class RAGContext(BaseModel):
    """Context retrieved by the RAG Retrieval Module before LLM call."""

    schema_chunks: list[str] = Field(default_factory=list)
    examples: list[Example] = Field(default_factory=list)
    metrics: list[MetricDef] = Field(default_factory=list)


# --- Agent models ---


class ToolCallRecord(BaseModel):
    """Record of a single tool call made by the agent."""

    tool_name: str
    tool_input: dict[str, Any] = Field(default_factory=dict)
    tool_output: Any = None


class AgentResponse(BaseModel):
    """Structured response from the single LLM agent."""

    status: str  # success | out_of_scope | clarification | error
    sql: str | None = None
    results: dict[str, Any] | None = None
    explanation: str = ""
    tool_calls: list[ToolCallRecord] = Field(default_factory=list)
    total_tokens: int = 0
    latency_ms: int = 0


# --- Audit models ---


class AuditRecord(BaseModel):
    """Audit log entry for compliance (Banking domain requirement)."""

    question: str
    generated_sql: str | None = None
    row_count: int | None = None
    status: str = "pending"
    error_message: str | None = None
    latency_ms: int = 0
    tool_calls_count: int = 0
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
    """Request body for POST /api/feedback — user correction."""

    question: str
    wrong_sql: str | None = None
    correct_sql: str
