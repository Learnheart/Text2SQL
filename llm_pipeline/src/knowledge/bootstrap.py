"""Knowledge Layer Bootstrap — initializes all knowledge components at startup.

10-step boot process (~5-8 seconds total):
1. Parse schema.json
2. Load schema table/column metadata
3. Detect FK relationships (from schema.json)
4. Load Semantic Layer YAML
5. Merge schema + semantic
6. Create schema chunks (cluster-based)
7. Generate embeddings with bge-m3
8. Upsert to pgvector
9. Load Example Store
10. Index example embeddings
"""

from __future__ import annotations

import logging
import time

from src.knowledge.example_store import ExampleStore
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.vector_store import PgVectorStore
from src.rag.chunking import create_chunks
from src.rag.embedding import EmbeddingService

logger = logging.getLogger(__name__)


class KnowledgeBase:
    """Holds all initialized knowledge components.

    Created by the bootstrap process, then injected into pipeline components.
    """

    def __init__(
        self,
        semantic_layer: SemanticLayer,
        example_store: ExampleStore,
        vector_store: PgVectorStore,
        embedding_service: EmbeddingService,
    ) -> None:
        self.semantic_layer = semantic_layer
        self.example_store = example_store
        self.vector_store = vector_store
        self.embedding_service = embedding_service


async def bootstrap_knowledge(
    vector_store: PgVectorStore | None = None,
    embedding_service: EmbeddingService | None = None,
) -> KnowledgeBase:
    """Run the full Knowledge Layer Boot Process.

    Returns a KnowledgeBase instance with all components initialized.
    """
    total_start = time.perf_counter()
    logger.info("Starting Knowledge Layer bootstrap...")

    # Step 1-3: Parse schema and relationships (handled by chunking module)
    t0 = time.perf_counter()
    chunks = create_chunks()
    logger.info("Steps 1-3: Schema parsed, %d chunks created (%.0fms)", len(chunks), (time.perf_counter() - t0) * 1000)

    # Step 4: Load Semantic Layer
    t0 = time.perf_counter()
    semantic_layer = SemanticLayer()
    logger.info(
        "Step 4: Semantic Layer loaded — %d metrics, %d aliases, %d rules (%.0fms)",
        len(semantic_layer.get_all_metrics()),
        len(semantic_layer.aliases),
        len(semantic_layer.business_rules),
        (time.perf_counter() - t0) * 1000,
    )

    # Step 5: Merge (implicit — chunks already include schema, semantic used separately)

    # Step 6: Already done in step 1-3

    # Step 7: Generate embeddings
    t0 = time.perf_counter()
    emb_service = embedding_service or EmbeddingService()
    chunk_texts = [c["text"] for c in chunks]
    chunk_embeddings = emb_service.embed_batch(chunk_texts)
    logger.info("Step 7: Schema embeddings generated (%.0fms)", (time.perf_counter() - t0) * 1000)

    # Step 8: Upsert schema embeddings to pgvector
    t0 = time.perf_counter()
    vs = vector_store or PgVectorStore(dimension=emb_service.dimension)
    if not vector_store:
        await vs.init()

    await vs.upsert(
        collection="schema_chunks",
        ids=[c["id"] for c in chunks],
        documents=chunk_texts,
        embeddings=chunk_embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )
    logger.info("Step 8: Schema embeddings upserted to pgvector (%.0fms)", (time.perf_counter() - t0) * 1000)

    # Step 9: Load Example Store
    t0 = time.perf_counter()
    example_store = ExampleStore()
    logger.info("Step 9: Example Store loaded — %d examples (%.0fms)", len(example_store.examples), (time.perf_counter() - t0) * 1000)

    # Step 10: Index example embeddings
    t0 = time.perf_counter()
    questions = example_store.get_questions()
    if questions:
        example_embeddings = emb_service.embed_batch(questions)
        await vs.upsert(
            collection="examples",
            ids=[f"example_{i}" for i in range(len(questions))],
            documents=questions,
            embeddings=example_embeddings,
            metadatas=[{"question": q, "index": i} for i, q in enumerate(questions)],
        )
    logger.info("Step 10: Example embeddings indexed (%.0fms)", (time.perf_counter() - t0) * 1000)

    total_ms = (time.perf_counter() - total_start) * 1000
    logger.info("Knowledge Layer bootstrap complete (total: %.0fms)", total_ms)

    return KnowledgeBase(
        semantic_layer=semantic_layer,
        example_store=example_store,
        vector_store=vs,
        embedding_service=emb_service,
    )
