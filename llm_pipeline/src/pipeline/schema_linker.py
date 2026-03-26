"""Schema Linker [CODE] — Deterministic context assembly for SQL Generator.

Steps:
1. Vector search: Embed question → find top-k schema chunks (cosine similarity)
2. Dict lookup: Query Semantic Layer for relevant metrics, aliases, enums
3. JOIN resolution: From matched tables, determine JOIN paths
4. Context assembly: Package everything into a ContextPackage

No LLM is used — this is pure retrieval and lookup.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import settings
from src.models.schemas import ContextPackage, Example
from src.knowledge.bootstrap import KnowledgeBase
from src.pipeline.state import PipelineState

if TYPE_CHECKING:
    from src.session_logger import SessionLogger

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "schema.json"

# JOIN map: defines how tables connect
_JOIN_MAP: dict[str, list[dict[str, str]]] = {}
_SCHEMA_LOADED = False


def _load_join_map() -> None:
    """Build JOIN map from schema.json relationships."""
    global _JOIN_MAP, _SCHEMA_LOADED
    if _SCHEMA_LOADED:
        return

    with open(_SCHEMA_PATH, encoding="utf-8") as f:
        tables = json.load(f)

    for table in tables:
        table_name = table["name"]
        for rel in table.get("relationships", []):
            from_col = rel["from"]  # e.g., "employees.branch_id"
            to_col = rel["to"]      # e.g., "branches.id"
            key = tuple(sorted([from_col.split(".")[0], to_col.split(".")[0]]))
            _JOIN_MAP[f"{key[0]}:{key[1]}"] = [{
                "from": from_col,
                "to": to_col,
                "type": rel.get("type", "many-to-one"),
            }]

    _SCHEMA_LOADED = True


async def link_schema(
    state: PipelineState,
    *,
    knowledge: KnowledgeBase,
    session_log: SessionLogger | None = None,
) -> PipelineState:
    """Assemble context package for the SQL Generator.

    Processing time target: ~150ms.
    """
    question = state["question"]

    if session_log:
        session_log.step(3, "SCHEMA_LINKER", f"Assembling context for: {question[:80]}")

    # Step 1: Vector search — find relevant schema chunks
    t0 = time.perf_counter()
    query_embedding = knowledge.embedding_service.embed(question)
    schema_results = await knowledge.vector_store.query(
        collection="schema_chunks",
        query_embedding=query_embedding,
        top_k=settings.schema_top_k,
    )
    schema_chunks = [r["document"] for r in schema_results]
    if session_log:
        session_log.detail("SCHEMA_LINKER", f"Vector search: {len(schema_chunks)} chunks ({int((time.perf_counter() - t0) * 1000)}ms)")

    # Step 2a: Vector search — find similar examples for few-shot
    t0 = time.perf_counter()
    example_results = await knowledge.vector_store.query(
        collection="examples",
        query_embedding=query_embedding,
        top_k=settings.example_top_k,
    )

    # Map back to Example objects
    examples: list[Example] = []
    for r in example_results:
        idx = r["metadata"].get("index")
        if idx is not None:
            found = knowledge.example_store.find_by_indices([int(idx)])
            examples.extend(found)
        else:
            question_text = r["metadata"].get("question", "")
            for ex in knowledge.example_store.examples:
                if ex.question == question_text:
                    examples.append(ex)
                    break

    if session_log:
        session_log.detail("SCHEMA_LINKER", f"Example search: {len(examples)} examples ({int((time.perf_counter() - t0) * 1000)}ms)")

    # Step 2b: Dict lookup — find relevant metrics
    t0 = time.perf_counter()
    metrics = knowledge.semantic_layer.find_relevant_metrics(question)
    if session_log:
        metric_names = [m.name for m in metrics]
        session_log.detail("SCHEMA_LINKER", f"Metric lookup: {metric_names} ({int((time.perf_counter() - t0) * 1000)}ms)")

    # Step 3: JOIN resolution — determine join hints from matched tables
    _load_join_map()
    matched_tables = set()
    for chunk in schema_chunks:
        for line in chunk.split("\n"):
            if line.startswith("Table: "):
                matched_tables.add(line.replace("Table: ", "").strip())

    join_hints = _resolve_joins(matched_tables)

    # Step 4: Assemble Context Package
    context = ContextPackage(
        schema_chunks=schema_chunks,
        examples=examples,
        metrics=metrics,
        join_hints=join_hints,
        business_rules=knowledge.semantic_layer.business_rules,
        sensitive_columns=knowledge.semantic_layer.sensitive_columns,
    )

    if session_log:
        session_log.detail(
            "SCHEMA_LINKER",
            f"Context assembled: {len(schema_chunks)} chunks, {len(examples)} examples, "
            f"{len(metrics)} metrics, {len(join_hints)} joins",
        )

    return {**state, "context_package": context}


def _resolve_joins(tables: set[str]) -> list[str]:
    """Given a set of tables, find all JOIN paths between them."""
    if len(tables) < 2:
        return []

    hints: list[str] = []
    table_list = sorted(tables)

    for i, t1 in enumerate(table_list):
        for t2 in table_list[i + 1:]:
            key = f"{min(t1, t2)}:{max(t1, t2)}"
            if key in _JOIN_MAP:
                for join_info in _JOIN_MAP[key]:
                    hints.append(f"{join_info['from']} = {join_info['to']}")

    return hints
