"""RAG Retrieval Module — retrieves context before LLM call."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from src.config import settings
from src.models.schemas import RAGContext
from src.rag.embedding import EmbeddingService
from src.knowledge.vector_store import VectorStore
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore

if TYPE_CHECKING:
    from src.session_logger import SessionLogger


class RAGRetrieval:
    """Retrieves schema chunks, similar examples, and relevant metrics for a question."""

    def __init__(
        self,
        embedding_service: EmbeddingService,
        vector_store: VectorStore,
        semantic_layer: SemanticLayer,
        example_store: ExampleStore,
    ) -> None:
        self._embedder = embedding_service
        self._vector_store = vector_store
        self._semantic_layer = semantic_layer
        self._example_store = example_store

    def retrieve(self, question: str, *, session_log: SessionLogger | None = None) -> RAGContext:
        """Retrieve RAG context for a question (deterministic, no LLM)."""
        # 1. Embed question
        t0 = time.perf_counter()
        query_embedding = self._embedder.embed(question)
        embed_ms = int((time.perf_counter() - t0) * 1000)
        if session_log:
            session_log.detail("RAG_RETRIEVAL", f"Question embedded, dim={len(query_embedding)} ({embed_ms}ms)")

        # 2. Vector search schema chunks
        t0 = time.perf_counter()
        schema_results = self._vector_store.query(
            "schema_chunks",
            query_embedding,
            top_k=settings.rag_schema_top_k,
        )
        schema_chunks = [r["document"] for r in schema_results]
        schema_ms = int((time.perf_counter() - t0) * 1000)
        if session_log:
            session_log.detail("RAG_RETRIEVAL", f"Schema vector search: {len(schema_chunks)} chunks ({schema_ms}ms)")

        # 3. Vector search similar examples
        t0 = time.perf_counter()
        example_results = self._vector_store.query(
            "examples",
            query_embedding,
            top_k=settings.rag_example_top_k,
        )
        # Map back to Example objects
        examples = []
        for r in example_results:
            question_text = r["metadata"].get("question", "")
            for ex in self._example_store.examples:
                if ex.question == question_text:
                    examples.append(ex)
                    break
        example_ms = int((time.perf_counter() - t0) * 1000)
        if session_log:
            session_log.detail("RAG_RETRIEVAL", f"Example vector search: {len(examples)} examples ({example_ms}ms)")

        # 4. Keyword match metrics
        t0 = time.perf_counter()
        metrics = self._semantic_layer.find_relevant_metrics(question)
        metric_ms = int((time.perf_counter() - t0) * 1000)
        if session_log:
            metric_names = [m.name for m in metrics]
            session_log.detail("RAG_RETRIEVAL", f"Metric keyword match: {metric_names} ({metric_ms}ms)")

        return RAGContext(
            schema_chunks=schema_chunks,
            examples=examples,
            metrics=metrics,
        )
