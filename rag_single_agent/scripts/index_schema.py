"""One-time script: chunk schema + embed + upsert into ChromaDB.

Usage:
    python -m scripts.index_schema
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.rag.chunking import create_chunks
from src.rag.embedding import EmbeddingService
from src.knowledge.vector_store import VectorStore
from src.knowledge.example_store import ExampleStore


def main() -> None:
    embedder = EmbeddingService()
    store = VectorStore()

    # --- 1. Index schema chunks ---
    print("Creating schema chunks...")
    chunks = create_chunks()
    print(f"  {len(chunks)} chunks created")

    print("Embedding schema chunks...")
    chunk_texts = [c["text"] for c in chunks]
    chunk_embeddings = embedder.embed_batch(chunk_texts)

    print("Upserting schema chunks into ChromaDB...")
    store.reset_collection("schema_chunks")
    store.upsert(
        collection_name="schema_chunks",
        ids=[c["id"] for c in chunks],
        documents=chunk_texts,
        embeddings=chunk_embeddings,
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"  {store.count('schema_chunks')} schema chunks indexed")

    # --- 2. Index example questions ---
    print("Loading golden queries...")
    example_store = ExampleStore()
    questions = example_store.get_questions()
    print(f"  {len(questions)} examples loaded")

    print("Embedding example questions...")
    example_embeddings = embedder.embed_batch(questions)

    # Store full Q+SQL as document for retrieval
    example_docs = [
        f"Q: {ex.question}\nSQL: {ex.sql}"
        for ex in example_store.examples
    ]

    print("Upserting examples into ChromaDB...")
    store.reset_collection("examples")
    store.upsert(
        collection_name="examples",
        ids=[f"example_{i}" for i in range(len(questions))],
        documents=example_docs,
        embeddings=example_embeddings,
        metadatas=[{"question": q} for q in questions],
    )
    print(f"  {store.count('examples')} examples indexed")

    # --- 3. Quick verification ---
    print("\n--- Verification ---")
    test_query = "total revenue this month"
    test_embedding = embedder.embed(test_query)

    schema_results = store.query("schema_chunks", test_embedding, top_k=3)
    print(f"Query: '{test_query}'")
    print(f"Top schema chunks: {[r['metadata'].get('cluster', '') for r in schema_results]}")

    example_results = store.query("examples", test_embedding, top_k=2)
    print(f"Top examples: {[r['metadata'].get('question', '')[:60] for r in example_results]}")

    print("\nDone! ChromaDB is ready.")


if __name__ == "__main__":
    main()
