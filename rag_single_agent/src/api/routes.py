"""REST API routes."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from src.models.schemas import QueryRequest, QueryResponse, FeedbackRequest, AuditRecord
from src.agent.response_parser import format_response_for_api
from src.api.app import state
from src.session_logger import SessionLogger

router = APIRouter()


@router.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    """Main endpoint: ask a question, get SQL + results + explanation."""
    session_log = SessionLogger(question=request.question)
    session_log.info("REQUEST", f"Received query: {request.question[:200]}")

    try:
        agent_response = await state.agent.run(request.question, session_log=session_log)
    except Exception as e:
        session_log.error("REQUEST", f"Agent failed: {e}")
        session_log.close()
        raise HTTPException(status_code=500, detail=str(e))

    # Audit log
    audit = AuditRecord(
        question=request.question,
        generated_sql=agent_response.sql,
        row_count=agent_response.results.get("row_count") if agent_response.results else None,
        status=agent_response.status,
        latency_ms=agent_response.latency_ms,
        tool_calls_count=len(agent_response.tool_calls),
        tokens_used=agent_response.total_tokens,
        model_used="claude-sonnet-4-6",
    )
    await state.audit_logger.log(audit)

    session_log.info("AUDIT", f"Audit record logged (session={session_log.session_id})")
    session_log.close()

    return format_response_for_api(agent_response)


@router.get("/api/health")
async def health():
    """Health check."""
    return {"status": "ok", "version": "0.1.0"}


@router.post("/api/feedback")
async def feedback(request: FeedbackRequest):
    """Submit a correction for a wrong SQL result."""
    # For now just acknowledge — will store in user_corrections table later
    return {"status": "received", "question": request.question}
