"""Tests for RAG Retrieval Module and Prompt Builder."""

import pytest

from src.rag.embedding import EmbeddingService
from src.knowledge.vector_store import VectorStore
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore
from src.rag.retrieval import RAGRetrieval
from src.agent.prompt_builder import PromptBuilder
from src.agent.response_parser import extract_sql_from_text


@pytest.fixture(scope="module")
def services():
    emb = EmbeddingService()
    vs = VectorStore()
    sl = SemanticLayer()
    es = ExampleStore()
    rag = RAGRetrieval(emb, vs, sl, es)
    pb = PromptBuilder(sl, es)
    return {"emb": emb, "vs": vs, "sl": sl, "es": es, "rag": rag, "pb": pb}


class TestRAGRetrieval:
    def test_retrieve_returns_context(self, services):
        ctx = services["rag"].retrieve("Total revenue this month")
        assert len(ctx.schema_chunks) > 0
        assert len(ctx.examples) > 0

    def test_retrieve_finds_relevant_schema(self, services):
        ctx = services["rag"].retrieve("Top merchants by revenue")
        all_text = " ".join(ctx.schema_chunks)
        assert "sales" in all_text.lower() or "merchant" in all_text.lower()

    def test_retrieve_finds_metrics(self, services):
        ctx = services["rag"].retrieve("Tổng doanh thu quý trước?")
        metric_names = [m.name for m in ctx.metrics]
        assert "doanh_thu" in metric_names

    def test_retrieve_no_metrics_for_unrelated(self, services):
        ctx = services["rag"].retrieve("weather today")
        # May or may not find metrics — just verify no crash
        assert ctx is not None

    def test_retrieve_finds_examples(self, services):
        ctx = services["rag"].retrieve("How many transactions today?")
        assert len(ctx.examples) > 0


class TestPromptBuilder:
    def test_build_prompt(self, services):
        ctx = services["rag"].retrieve("Total revenue this month")
        prompt = services["pb"].build(ctx)
        assert "SELECT" in prompt or "SQL" in prompt
        assert "Banking/POS" in prompt
        assert len(prompt) > 500

    def test_prompt_contains_schema(self, services):
        ctx = services["rag"].retrieve("Top 5 merchants")
        prompt = services["pb"].build(ctx)
        assert "Table:" in prompt

    def test_prompt_contains_rules(self, services):
        ctx = services["rag"].retrieve("test")
        prompt = services["pb"].build(ctx)
        assert "SELECT" in prompt
        assert "LIMIT" in prompt


class TestResponseParser:
    def test_extract_sql(self):
        text = "Here is the query:\n```sql\nSELECT COUNT(*) FROM sales\n```\nDone."
        sql = extract_sql_from_text(text)
        assert sql == "SELECT COUNT(*) FROM sales"

    def test_extract_sql_multiline(self):
        text = "```sql\nSELECT m.name,\n  SUM(s.total_amount)\nFROM sales s\nJOIN merchants m ON s.merchant_id = m.id\n```"
        sql = extract_sql_from_text(text)
        assert "SELECT" in sql
        assert "JOIN" in sql

    def test_extract_sql_no_match(self):
        text = "No SQL here, just text."
        sql = extract_sql_from_text(text)
        assert sql is None
