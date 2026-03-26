from __future__ import annotations

from pathlib import Path

import yaml

from src.models.schemas import MetricDef

_DEFAULT_PATH = Path(__file__).resolve().parents[2] / "config" / "semantic_layer.yaml"


class SemanticLayer:
    """Loads and queries the semantic layer YAML config."""

    def __init__(self, path: Path | str = _DEFAULT_PATH) -> None:
        with open(path, encoding="utf-8") as f:
            self._data: dict = yaml.safe_load(f)

        self._metrics: dict[str, MetricDef] = {}
        for key, val in self._data.get("metrics", {}).items():
            self._metrics[key] = MetricDef(
                name=key,
                sql=val["sql"],
                filter=val.get("filter", ""),
                aliases=val.get("aliases", []),
                description=val.get("description", ""),
            )

        self.aliases: dict[str, str] = self._data.get("aliases", {})
        self.sensitive_columns: list[str] = self._data.get("sensitive_columns", [])
        self.enums: dict[str, list[str]] = self._data.get("enums", {})
        self.business_rules: list[str] = self._data.get("business_rules", [])

    # --- Public API ---

    def get_metric(self, name: str) -> MetricDef | None:
        """Exact or alias lookup for a metric."""
        if name in self._metrics:
            return self._metrics[name]
        name_lower = name.lower().strip()
        for metric in self._metrics.values():
            if name_lower in [a.lower() for a in metric.aliases]:
                return metric
        return None

    def find_relevant_metrics(self, question: str) -> list[MetricDef]:
        """Keyword matching: return metrics whose aliases appear in the question."""
        q_lower = question.lower()
        results: list[MetricDef] = []
        for metric in self._metrics.values():
            for alias in metric.aliases:
                if alias.lower() in q_lower:
                    results.append(metric)
                    break
        return results

    def get_all_metrics(self) -> list[MetricDef]:
        return list(self._metrics.values())

    def is_sensitive(self, table_column: str) -> bool:
        """Check if a table.column is marked as sensitive."""
        return table_column in self.sensitive_columns

    def get_enum_values(self, table_column: str) -> list[str] | None:
        return self.enums.get(table_column)

    def format_for_prompt(self, metrics: list[MetricDef] | None = None) -> str:
        """Format metric definitions as text for LLM prompt."""
        target = metrics if metrics is not None else self.get_all_metrics()
        if not target:
            return ""
        lines: list[str] = []
        for m in target:
            line = f"- {m.name}: {m.sql}"
            if m.filter:
                line += f" (WHERE {m.filter})"
            if m.description:
                line += f" — {m.description}"
            lines.append(line)
        return "\n".join(lines)
