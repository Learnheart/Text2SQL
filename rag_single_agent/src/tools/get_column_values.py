"""Tool: get_column_values — Get DISTINCT values of a column (enum lookup)."""

from __future__ import annotations

import logging

from src.data_access.connection import DatabasePool
from src.knowledge.semantic_layer import SemanticLayer

logger = logging.getLogger(__name__)


async def get_column_values(
    table: str,
    column: str,
    pool: DatabasePool,
    semantic_layer: SemanticLayer,
    limit: int = 50,
) -> dict:
    """Get distinct values of a column, useful for enum lookups."""
    logger.debug("Column values lookup: %s.%s", table, column)

    # Block sensitive columns
    table_column = f"{table}.{column}"
    if semantic_layer.is_sensitive(table_column):
        logger.warning("Blocked sensitive column access: %s", table_column)
        return {"error": f"Column '{table_column}' is marked as sensitive and cannot be queried"}

    # Basic SQL injection prevention: only alphanumeric + underscore
    if not table.replace("_", "").isalnum() or not column.replace("_", "").isalnum():
        logger.warning("Blocked invalid table/column name: %s.%s", table, column)
        return {"error": "Invalid table or column name"}

    sql = f"SELECT DISTINCT {column} FROM {table} ORDER BY {column} LIMIT {limit}"
    result = await pool.execute(sql)

    if "error" in result:
        logger.error("Column values error: %s", result["error"])
        return result

    values = [row[0] for row in result.get("rows", []) if row]
    logger.debug("Column values: %s.%s → %d distinct values", table, column, len(values))
    return {
        "table": table,
        "column": column,
        "values": [str(v) if v is not None else None for v in values],
        "count": len(values),
    }


TOOL_DEFINITION = {
    "name": "get_column_values",
    "description": (
        "Get the distinct values of a column in a table. "
        "Useful for discovering valid enum values (e.g., sales.status → ['completed', 'pending', 'failed']). "
        "Returns up to 50 distinct values. Sensitive columns (cvv, card_number, dob, email) are blocked."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "table": {
                "type": "string",
                "description": "Table name (e.g., 'sales', 'customers')",
            },
            "column": {
                "type": "string",
                "description": "Column name (e.g., 'status', 'kyc_status')",
            },
        },
        "required": ["table", "column"],
    },
}
