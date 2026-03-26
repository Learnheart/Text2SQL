"""Tool: execute_sql — Executes a SELECT query on PostgreSQL (read-only)."""

from __future__ import annotations

import logging
import re

from src.data_access.connection import DatabasePool

logger = logging.getLogger(__name__)


def _add_limit(sql: str, limit: int = 1000) -> str:
    """Add LIMIT clause if missing."""
    if not re.search(r"\bLIMIT\b", sql, re.IGNORECASE):
        sql = sql.rstrip().rstrip(";")
        sql += f" LIMIT {limit};"
    return sql


async def execute_sql(sql: str, pool: DatabasePool) -> dict:
    """Execute a SQL query with safety checks.

    Safety:
      - Only SELECT allowed (block INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE)
      - Auto-adds LIMIT 1000 if missing
      - Read-only connection + statement_timeout from pool
    """
    stripped = sql.strip()

    # Block non-SELECT statements
    first_keyword = stripped.split()[0].upper() if stripped else ""
    if first_keyword not in ("SELECT", "WITH", "EXPLAIN"):
        logger.warning("Blocked non-SELECT statement: %s", first_keyword)
        return {"error": "Only SELECT queries are allowed"}

    # Block dangerous keywords anywhere in the query
    dangerous = r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE)\b"
    if re.search(dangerous, stripped, re.IGNORECASE):
        logger.warning("Blocked dangerous keyword in SQL: %s", stripped[:100])
        return {"error": "Only SELECT queries are allowed. DML/DDL statements are blocked."}

    # Add LIMIT if missing
    sql = _add_limit(stripped)
    logger.debug("Executing SQL: %s", sql[:200])

    # Execute
    result = await pool.execute(sql)

    # Serialize UUIDs and other non-JSON types to strings
    if "rows" in result:
        result["rows"] = [
            [str(v) if not isinstance(v, (int, float, str, bool, type(None))) else v for v in row]
            for row in result["rows"]
        ]

    if "error" in result:
        logger.error("SQL execution error: %s", result["error"])
    else:
        logger.debug("SQL result: %d rows in %dms", result.get("row_count", 0), result.get("execution_time_ms", 0))

    return result


# LLM tool definition
TOOL_DEFINITION = {
    "name": "execute_sql",
    "description": (
        "Execute a read-only SELECT SQL query on the PostgreSQL database. "
        "Returns columns, rows, and row_count. Only SELECT statements are allowed. "
        "A LIMIT of 1000 is auto-added if missing. Timeout is 30 seconds."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {
                "type": "string",
                "description": "The SQL SELECT query to execute",
            }
        },
        "required": ["sql"],
    },
}
