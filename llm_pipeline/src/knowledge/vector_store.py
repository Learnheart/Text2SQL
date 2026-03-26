"""pgvector-based vector store — replaces ChromaDB from Phase 1.

Uses PostgreSQL pgvector extension for storing and searching embeddings.
This integrates vector storage directly with the primary database.
"""

from __future__ import annotations

import logging
from typing import Any

import asyncpg

from src.config import settings

logger = logging.getLogger(__name__)


class PgVectorStore:
    """Vector store backed by PostgreSQL pgvector extension.

    Tables created:
    - schema_embeddings: Schema chunk embeddings for retrieval
    - example_embeddings: Golden query example embeddings for few-shot
    """

    def __init__(self, dimension: int | None = None) -> None:
        self._dimension = dimension or settings.embedding_dimension
        self._pool: asyncpg.Pool | None = None

    async def init(self, pool: asyncpg.Pool | None = None) -> None:
        """Initialize with an existing pool or create a new one."""
        if pool:
            self._pool = pool
        else:
            self._pool = await asyncpg.create_pool(
                dsn=settings.asyncpg_dsn,
                min_size=1,
                max_size=3,
            )

        await self._ensure_tables()
        logger.info("PgVectorStore initialized (dimension=%d)", self._dimension)

    async def _ensure_tables(self) -> None:
        """Create pgvector extension and embedding tables if they don't exist."""
        if not self._pool:
            return

        async with self._pool.acquire() as conn:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS schema_embeddings (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    metadata JSONB DEFAULT '{{}}',
                    embedding vector({self._dimension})
                )
            """)

            await conn.execute(f"""
                CREATE TABLE IF NOT EXISTS example_embeddings (
                    id TEXT PRIMARY KEY,
                    document TEXT NOT NULL,
                    metadata JSONB DEFAULT '{{}}',
                    embedding vector({self._dimension})
                )
            """)

            # Create HNSW indexes for fast similarity search
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_schema_embeddings_hnsw
                ON schema_embeddings USING hnsw (embedding vector_cosine_ops)
            """)
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_example_embeddings_hnsw
                ON example_embeddings USING hnsw (embedding vector_cosine_ops)
            """)

    async def upsert(
        self,
        collection: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict[str, Any]] | None = None,
    ) -> None:
        """Upsert documents with embeddings into a collection table."""
        if not self._pool:
            raise RuntimeError("PgVectorStore not initialized")

        table = self._resolve_table(collection)
        metas = metadatas or [{}] * len(ids)

        async with self._pool.acquire() as conn:
            for i in range(len(ids)):
                embedding_str = "[" + ",".join(str(v) for v in embeddings[i]) + "]"
                import json
                meta_json = json.dumps(metas[i])

                await conn.execute(
                    f"""
                    INSERT INTO {table} (id, document, metadata, embedding)
                    VALUES ($1, $2, $3::jsonb, $4::vector)
                    ON CONFLICT (id) DO UPDATE SET
                        document = EXCLUDED.document,
                        metadata = EXCLUDED.metadata,
                        embedding = EXCLUDED.embedding
                    """,
                    ids[i],
                    documents[i],
                    meta_json,
                    embedding_str,
                )

        logger.debug("Upserted %d documents into %s", len(ids), table)

    async def query(
        self,
        collection: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        """Query collection by embedding using cosine similarity. Returns top-k results."""
        if not self._pool:
            raise RuntimeError("PgVectorStore not initialized")

        table = self._resolve_table(collection)
        embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                f"""
                SELECT id, document, metadata,
                       1 - (embedding <=> $1::vector) AS similarity
                FROM {table}
                ORDER BY embedding <=> $1::vector
                LIMIT $2
                """,
                embedding_str,
                top_k,
            )

        results: list[dict[str, Any]] = []
        for row in rows:
            import json
            results.append({
                "id": row["id"],
                "document": row["document"],
                "metadata": json.loads(row["metadata"]) if row["metadata"] else {},
                "similarity": float(row["similarity"]),
            })

        return results

    async def count(self, collection: str) -> int:
        if not self._pool:
            return 0

        table = self._resolve_table(collection)
        async with self._pool.acquire() as conn:
            result = await conn.fetchval(f"SELECT COUNT(*) FROM {table}")
            return result or 0

    async def reset_collection(self, collection: str) -> None:
        if not self._pool:
            return

        table = self._resolve_table(collection)
        async with self._pool.acquire() as conn:
            await conn.execute(f"TRUNCATE TABLE {table}")

        logger.info("Reset collection: %s", table)

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None

    @staticmethod
    def _resolve_table(collection: str) -> str:
        """Map collection name to table name."""
        mapping = {
            "schema_chunks": "schema_embeddings",
            "schema_embeddings": "schema_embeddings",
            "examples": "example_embeddings",
            "example_embeddings": "example_embeddings",
        }
        table = mapping.get(collection)
        if not table:
            raise ValueError(f"Unknown collection: {collection}. Use 'schema_chunks' or 'examples'.")
        return table
