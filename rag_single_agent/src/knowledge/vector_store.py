"""ChromaDB vector store wrapper for schema chunks and examples."""

from __future__ import annotations

import chromadb
from chromadb.config import Settings as ChromaSettings

from src.config import settings


class VectorStore:
    """Manages ChromaDB collections for schema and example embeddings."""

    def __init__(self, persist_dir: str | None = None) -> None:
        self._persist_dir = persist_dir or settings.chroma_persist_dir
        self._client: chromadb.ClientAPI | None = None

    def _get_client(self) -> chromadb.ClientAPI:
        if self._client is None:
            self._client = chromadb.PersistentClient(
                path=self._persist_dir,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
        return self._client

    def get_or_create_collection(self, name: str) -> chromadb.Collection:
        return self._get_client().get_or_create_collection(
            name=name,
            metadata={"hnsw:space": "cosine"},
        )

    def upsert(
        self,
        collection_name: str,
        ids: list[str],
        documents: list[str],
        embeddings: list[list[float]],
        metadatas: list[dict] | None = None,
    ) -> None:
        collection = self.get_or_create_collection(collection_name)
        collection.upsert(
            ids=ids,
            documents=documents,
            embeddings=embeddings,
            metadatas=metadatas,
        )

    def query(
        self,
        collection_name: str,
        query_embedding: list[float],
        top_k: int = 5,
    ) -> list[dict]:
        """Query collection by embedding. Returns list of {id, document, metadata, distance}."""
        collection = self.get_or_create_collection(collection_name)
        if collection.count() == 0:
            return []

        results = collection.query(
            query_embeddings=[query_embedding],
            n_results=min(top_k, collection.count()),
            include=["documents", "metadatas", "distances"],
        )

        items: list[dict] = []
        for i in range(len(results["ids"][0])):
            items.append(
                {
                    "id": results["ids"][0][i],
                    "document": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "distance": results["distances"][0][i] if results["distances"] else 0.0,
                }
            )
        return items

    def count(self, collection_name: str) -> int:
        collection = self.get_or_create_collection(collection_name)
        return collection.count()

    def reset_collection(self, collection_name: str) -> None:
        client = self._get_client()
        try:
            client.delete_collection(collection_name)
        except Exception:
            pass
