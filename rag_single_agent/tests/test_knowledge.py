"""Tests for Knowledge Layer: semantic_layer, example_store, chunking, vector_store."""

from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore
from src.rag.chunking import create_chunks


class TestSemanticLayer:
    def setup_method(self):
        self.sl = SemanticLayer()

    def test_loads_metrics(self):
        metrics = self.sl.get_all_metrics()
        assert len(metrics) >= 15

    def test_get_metric_by_name(self):
        m = self.sl.get_metric("doanh_thu")
        assert m is not None
        assert "SUM" in m.sql

    def test_get_metric_by_alias(self):
        m = self.sl.get_metric("revenue")
        assert m is not None
        assert m.name == "doanh_thu"

    def test_get_metric_by_vietnamese_alias(self):
        m = self.sl.get_metric("tổng doanh thu")
        assert m is not None
        assert m.name == "doanh_thu"

    def test_get_metric_not_found(self):
        m = self.sl.get_metric("nonexistent_metric")
        assert m is None

    def test_find_relevant_metrics_doanh_thu(self):
        metrics = self.sl.find_relevant_metrics("Tổng doanh thu tháng 1?")
        names = [m.name for m in metrics]
        assert "doanh_thu" in names

    def test_find_relevant_metrics_refund(self):
        metrics = self.sl.find_relevant_metrics("What is the refund rate?")
        names = [m.name for m in metrics]
        assert "refund_rate" in names

    def test_find_relevant_metrics_no_match(self):
        metrics = self.sl.find_relevant_metrics("thời tiết hôm nay")
        assert len(metrics) == 0

    def test_sensitive_columns(self):
        assert self.sl.is_sensitive("cards.cvv")
        assert self.sl.is_sensitive("cards.card_number")
        assert self.sl.is_sensitive("customers.dob")
        assert not self.sl.is_sensitive("sales.total_amount")

    def test_enum_values(self):
        vals = self.sl.get_enum_values("sales.status")
        assert vals is not None
        assert "completed" in vals

    def test_aliases(self):
        assert self.sl.aliases["giao dịch"] == "sales"
        assert self.sl.aliases["khách hàng"] == "customers"

    def test_format_for_prompt(self):
        metrics = self.sl.find_relevant_metrics("doanh thu")
        text = self.sl.format_for_prompt(metrics)
        assert "doanh_thu" in text
        assert "SUM" in text


class TestExampleStore:
    def setup_method(self):
        self.es = ExampleStore()

    def test_loads_examples(self):
        assert len(self.es.examples) >= 40

    def test_get_questions(self):
        questions = self.es.get_questions()
        assert len(questions) == len(self.es.examples)
        assert all(isinstance(q, str) for q in questions)

    def test_find_by_indices(self):
        result = self.es.find_by_indices([0, 1, 2])
        assert len(result) == 3

    def test_find_by_indices_out_of_range(self):
        result = self.es.find_by_indices([999])
        assert len(result) == 0

    def test_format_for_prompt(self):
        examples = self.es.find_by_indices([0, 1])
        text = self.es.format_for_prompt(examples)
        assert "Example 1:" in text
        assert "Q:" in text
        assert "SQL:" in text


class TestChunking:
    def test_create_chunks(self):
        chunks = create_chunks()
        assert len(chunks) == 7

    def test_chunk_structure(self):
        chunks = create_chunks()
        for c in chunks:
            assert "id" in c
            assert "text" in c
            assert "metadata" in c
            assert "cluster" in c["metadata"]
            assert "tables" in c["metadata"]

    def test_transaction_chunk_contains_sales(self):
        chunks = create_chunks()
        txn_chunk = next(c for c in chunks if c["id"] == "cluster_transaction_analytics")
        assert "sales" in txn_chunk["text"]
        assert "total_amount" in txn_chunk["text"]

    def test_customer_chunk_contains_accounts(self):
        chunks = create_chunks()
        cust_chunk = next(c for c in chunks if c["id"] == "cluster_customer_banking")
        assert "accounts" in cust_chunk["text"]
        assert "customers" in cust_chunk["text"]
