"""Tool: search_schema — Vector search for schema information."""

from __future__ import annotations

import logging

from src.rag.embedding import EmbeddingService
from src.knowledge.vector_store import VectorStore

logger = logging.getLogger(__name__)


async def search_schema(
    query: str,
    embedding_service: EmbeddingService,
    vector_store: VectorStore,
    top_k: int = 3,
) -> dict:
    """Search vector store for schema chunks relevant to the query."""
    logger.debug("Schema search query: %s", query)
    embedding = embedding_service.embed(query)
    results = vector_store.query("schema_chunks", embedding, top_k=top_k)

    if not results:
        logger.debug("Schema search: no results found")
        return {"results": [], "message": "No relevant schema found"}

    chunks = []
    for r in results:
        chunks.append({
            "cluster": r["metadata"].get("cluster", ""),
            "tables": r["metadata"].get("tables", ""),
            "content": r["document"],
            "similarity": round(1 - r["distance"], 3),
        })

    logger.debug("Schema search: %d chunks found (top similarity: %.3f)", len(chunks), chunks[0]["similarity"])
    return {"results": chunks}


TOOL_DEFINITION = {
    "name": "search_schema",
    "description": (
        "Search the database schema for tables, columns, and relationships relevant to a query. "
        "Use this when you need additional schema information not provided in the initial context. "
        "Returns schema definitions including table names, column names, types, and relationships."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Description of the schema information you need (e.g., 'tables related to transfers')",
            }
        },
        "required": ["query"],
    },
}
