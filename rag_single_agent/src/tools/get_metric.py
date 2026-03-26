"""Tool: get_metric_definition — Lookup business metric SQL definition."""

from __future__ import annotations

import logging

from src.knowledge.semantic_layer import SemanticLayer

logger = logging.getLogger(__name__)


async def get_metric_definition(metric_name: str, semantic_layer: SemanticLayer) -> dict:
    """Look up the SQL definition of a business metric."""
    logger.debug("Metric lookup: %s", metric_name)
    metric = semantic_layer.get_metric(metric_name)

    if metric is None:
        available = [m.name for m in semantic_layer.get_all_metrics()]
        logger.debug("Metric '%s' not found. Available: %s", metric_name, available)
        return {
            "error": f"Metric '{metric_name}' not found",
            "available_metrics": available,
        }

    logger.debug("Metric found: %s → %s", metric.name, metric.sql)
    return {
        "name": metric.name,
        "sql": metric.sql,
        "filter": metric.filter,
        "aliases": metric.aliases,
        "description": metric.description,
    }


TOOL_DEFINITION = {
    "name": "get_metric_definition",
    "description": (
        "Look up the SQL definition of a business metric (e.g., 'doanh thu' → SUM(sales.total_amount)). "
        "Returns the SQL expression, required filters, and description. "
        "Use this when the question contains business terms that need to be translated to SQL."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "metric_name": {
                "type": "string",
                "description": "The name of the metric to look up (e.g., 'doanh thu', 'refund rate', 'revenue')",
            }
        },
        "required": ["metric_name"],
    },
}
