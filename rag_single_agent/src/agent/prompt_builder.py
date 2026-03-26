"""Prompt builder — assembles the system prompt from RAG context."""

from __future__ import annotations

from pathlib import Path

from src.models.schemas import RAGContext
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore

_TEMPLATE_PATH = Path(__file__).resolve().parents[2] / "config" / "prompts" / "system_prompt.txt"


class PromptBuilder:
    """Builds the full system prompt by injecting RAG context into the template."""

    def __init__(self, semantic_layer: SemanticLayer, example_store: ExampleStore) -> None:
        self._semantic_layer = semantic_layer
        self._example_store = example_store
        with open(_TEMPLATE_PATH, encoding="utf-8") as f:
            self._template = f.read()

    def build(self, rag_context: RAGContext) -> str:
        """Build system prompt with injected RAG context."""
        # Schema context
        schema_text = "\n\n".join(rag_context.schema_chunks) if rag_context.schema_chunks else "No schema context available."

        # Metric definitions
        metric_text = self._semantic_layer.format_for_prompt(rag_context.metrics) if rag_context.metrics else "No specific metrics matched."

        # Business rules
        rules = self._semantic_layer.business_rules
        rules_text = "\n".join(f"- {r}" for r in rules) if rules else "No special rules."

        # Few-shot examples
        examples_text = self._example_store.format_for_prompt(rag_context.examples) if rag_context.examples else "No examples available."

        return self._template.format(
            schema_context=schema_text,
            metric_definitions=metric_text,
            business_rules=rules_text,
            few_shot_examples=examples_text,
        )
