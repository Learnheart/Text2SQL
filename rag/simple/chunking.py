import json
import chromadb
from chromadb.utils import embedding_functions
from sentence_transformers import SentenceTransformer

def reformat_query(input_json):
    """
    Convert query examples into RAG-friendly format with text + metadata.
    """
    rag_docs = []
    for example in input_json:
        text = f"Question: {example['business_question']}\nExplanation: {example['explanation']}"

        # Store query in metadata
        rag_docs.append({
            "content": text,
            "metadata": {
                "query": example["query"]
            }
        })
    return rag_docs


def flatten_json_to_text(input_json):
    """
    Flatten a JSON list into text-only format (no metadata).
    """
    flattened = []
    for obj in input_json:
        lines = []
        for k, v in obj.items():
            lines.append(f"{k}: {v}")
        content = "\n".join(lines)

        flattened.append({
            "content": content,
            "metadata": None
        })
    return flattened


def reformat_with_metadata(input_json):
    """
    Reformat schema JSON into RAG-friendly format with table metadata.
    """
    reformatted = []
    for obj in input_json:
        # Flatten content
        lines = []
        for k, v in obj.items():
            lines.append(f"{k}: {v}")
        content = "\n".join(lines)

        # Metadata only keeps table name if present
        metadata = {"table": obj["name"]} if "name" in obj else None

        reformatted.append({
            "content": content,
            "metadata": metadata
        })
    return reformatted


def insert_chunks_to_chromadb(json_chunks, collection_name="schema_chunks"):
    """
    Insert reformatted chunks (list of dicts with content+metadata) into ChromaDB.
    """
    client = chromadb.PersistentClient(path="./simple_chunking_db")
    
    # Wrap SentenceTransformer inside Chroma's embedding wrapper
    embedding_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="BAAI/bge-large-en-v1.5"
    )

    collection = client.get_or_create_collection(
        name=collection_name,
        embedding_function=embedding_fn,
    )

    documents = [item["content"] for item in json_chunks]
    ids = [f"chunk_{i}" for i in range(len(json_chunks))]
    metadatas = [item.get("metadata") for item in json_chunks]

    collection.add(
        documents=documents,
        metadatas=metadatas,
        ids=ids
    )

    print(f"✅ Inserted {len(documents)} chunks into ChromaDB collection '{collection_name}'")
    return collection


if __name__ == "__main__":
    with open(r"C:\Projects\demo\RAG\text_to_sql\data\query.json", "r") as f:
        query_data = json.load(f)

    with open(r"C:\Projects\demo\RAG\text_to_sql\data\schema.json", "r") as f:
        schema = json.load(f)

    # Queries → include SQL in metadata
    query_formatted = reformat_query(query_data)

    # Schema → flatten + keep table name
    schema_formatted = reformat_with_metadata(schema)

    # Insert into Chroma
    query_collection = insert_chunks_to_chromadb(query_formatted, collection_name="query_samples")
    schema_collection = insert_chunks_to_chromadb(schema_formatted, collection_name="schema_samples")
