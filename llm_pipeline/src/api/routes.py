"""REST API routes for the LLM-in-the-middle pipeline.

Endpoints:
- POST /api/query  — Main: ask question, get SQL + results
- GET  /api/health — Health check
- POST /api/feedback — Submit correction for wrong SQL
"""

from __future__ import annotations

import time

from fastapi import APIRouter

from src.api.app import get_app_state
from src.models.schemas import (
    AuditRecord,
    FeedbackRequest,
    PipelineStatus,
    QueryRequest,
    QueryResponse,
)

router = APIRouter()


@router.post("/api/query")
async def query(request: QueryRequest) -> QueryResponse:
    """Main endpoint: ask a question, get SQL + results + explanation."""
    state = get_app_state()
    start = time.perf_counter()

    # Check cache first
    if state.cache.available:
        cached = await state.cache.get_query(request.question)
        if cached:
            return QueryResponse(**cached)

    # Run pipeline
    response = await state.pipeline.run(
        question=request.question,
        session_id=request.session_id,
    )

    # Build API response
    result = QueryResponse(
        status=response.status.value,
        sql=response.sql,
        results=response.results.model_dump() if response.results else None,
        explanation=response.explanation,
        metadata={
            "intent": response.intent.value,
            "attempts": response.attempts,
            "total_tokens": response.total_tokens,
            "latency_ms": response.latency_ms,
        },
    )

    # Cache successful results
    if response.status == PipelineStatus.SUCCESS and state.cache.available:
        await state.cache.set_query(request.question, result.model_dump())

    # Audit log
    await state.audit.log(AuditRecord(
        question=request.question,
        generated_sql=response.sql,
        row_count=response.results.row_count if response.results else None,
        status=response.status.value,
        latency_ms=response.latency_ms,
        attempts=response.attempts,
        tokens_used=response.total_tokens,
    ))

    return result


@router.get("/api/health")
async def health() -> dict:
    """Health check endpoint."""
    try:
        state = get_app_state()
        return {
            "status": "healthy",
            "cache": state.cache.available,
            "tracer": state.tracer.enabled,
        }
    except RuntimeError:
        return {"status": "starting"}


@router.post("/api/feedback")
async def feedback(request: FeedbackRequest) -> dict:
    """Submit user correction for a wrong SQL query."""
    # TODO: Store feedback in Example Store for future learning
    return {
        "status": "received",
        "message": "Feedback recorded. Thank you for helping improve the system.",
    }
