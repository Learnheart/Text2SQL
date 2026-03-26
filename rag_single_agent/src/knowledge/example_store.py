"""Example store — golden queries loaded from JSON, searchable via vector similarity."""

from __future__ import annotations

import json
from pathlib import Path

from src.models.schemas import Example

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "golden_queries.json"


class ExampleStore:
    """Manages golden query examples for few-shot prompting."""

    def __init__(self, path: Path | str = _DEFAULT_PATH) -> None:
        self._path = Path(path)
        self._examples: list[Example] = []
        self._load()

    def _load(self) -> None:
        with open(self._path, encoding="utf-8") as f:
            data = json.load(f)
        self._examples = [
            Example(
                question=item["question"],
                sql=item["sql"],
                explanation=item.get("explanation", ""),
            )
            for item in data
        ]

    @property
    def examples(self) -> list[Example]:
        return self._examples

    def get_questions(self) -> list[str]:
        """Return all example questions (for batch embedding)."""
        return [ex.question for ex in self._examples]

    def find_by_indices(self, indices: list[int]) -> list[Example]:
        """Return examples at given indices."""
        return [self._examples[i] for i in indices if 0 <= i < len(self._examples)]

    def format_for_prompt(self, examples: list[Example]) -> str:
        """Format examples as text for LLM prompt."""
        lines: list[str] = []
        for i, ex in enumerate(examples, 1):
            lines.append(f"Example {i}:")
            lines.append(f"  Q: {ex.question}")
            lines.append(f"  SQL: {ex.sql}")
            lines.append("")
        return "\n".join(lines)
