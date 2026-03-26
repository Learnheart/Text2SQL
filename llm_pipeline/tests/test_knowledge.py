"""Tests for the Knowledge Layer — Semantic Layer, Example Store."""

import pytest
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore


class TestSemanticLayer:
    @pytest.fixture
    def layer(self):
        return SemanticLayer()

    def test_loads_metrics(self, layer):
        metrics = layer.get_all_metrics()
        assert len(metrics) > 0

    def test_get_metric_by_name(self, layer):
        # Check a metric that should exist (doanh_thu is common)
        metrics = layer.get_all_metrics()
        if metrics:
            metric = layer.get_metric(metrics[0].name)
            assert metric is not None

    def test_get_metric_by_alias(self, layer):
        metrics = layer.get_all_metrics()
        for m in metrics:
            if m.aliases:
                result = layer.get_metric(m.aliases[0])
                assert result is not None
                break

    def test_find_relevant_metrics(self, layer):
        # Should find metrics when question contains relevant keywords
        metrics = layer.get_all_metrics()
        if metrics and metrics[0].aliases:
            alias = metrics[0].aliases[0]
            found = layer.find_relevant_metrics(f"Tôi muốn biết {alias}")
            assert len(found) > 0

    def test_nonexistent_metric(self, layer):
        assert layer.get_metric("xxxxnonexistent") is None

    def test_sensitive_columns_loaded(self, layer):
        assert len(layer.sensitive_columns) > 0

    def test_business_rules_loaded(self, layer):
        assert len(layer.business_rules) > 0

    def test_aliases_loaded(self, layer):
        assert len(layer.aliases) > 0

    def test_format_for_prompt(self, layer):
        text = layer.format_for_prompt()
        assert isinstance(text, str)
        assert len(text) > 0


class TestExampleStore:
    @pytest.fixture
    def store(self):
        return ExampleStore()

    def test_loads_examples(self, store):
        assert len(store.examples) > 0

    def test_get_questions(self, store):
        questions = store.get_questions()
        assert len(questions) == len(store.examples)
        assert all(isinstance(q, str) for q in questions)

    def test_find_by_indices(self, store):
        examples = store.find_by_indices([0, 1])
        assert len(examples) <= 2

    def test_find_by_invalid_index(self, store):
        examples = store.find_by_indices([9999])
        assert len(examples) == 0

    def test_format_for_prompt(self, store):
        if store.examples:
            text = store.format_for_prompt(store.examples[:2])
            assert "Example 1" in text
            assert "Q:" in text
            assert "SQL:" in text
