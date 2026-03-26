"""Response parser — extracts SQL and explanation from agent response."""

from __future__ import annotations

import re

from src.models.schemas import AgentResponse


def extract_sql_from_text(text: str) -> str | None:
    """Extract SQL from markdown code block in text."""
    pattern = r"```sql\s*(.*?)\s*```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return None


def format_response_for_api(agent_response: AgentResponse) -> dict:
    """Format AgentResponse for the REST API."""
    response = {
        "status": agent_response.status,
        "explanation": agent_response.explanation,
        "metadata": {
            "latency_ms": agent_response.latency_ms,
            "tool_calls": len(agent_response.tool_calls),
            "tokens": agent_response.total_tokens,
        },
    }

    if agent_response.sql:
        response["sql"] = agent_response.sql

    if agent_response.results:
        response["results"] = agent_response.results

    return response
