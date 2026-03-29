"""Cluster-based schema chunking — groups related tables into domain chunks."""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULT_SCHEMA_PATH = Path(__file__).resolve().parents[3] / "data" / "schema.json"

# Domain clusters: group related tables together for better retrieval.
CLUSTERS: list[dict] = [
    {
        "name": "transaction_analytics",
        "tables": ["sales", "terminals", "products"],
        "use_cases": "Revenue analysis, product performance, terminal activity, sales metrics",
    },
    {
        "name": "merchant",
        "tables": ["merchants"],
        "use_cases": "Merchant analytics, MCC analysis, merchant location",
    },
    {
        "name": "customer_banking",
        "tables": ["customers", "accounts", "cards"],
        "use_cases": "Customer analytics, account balances, card status, KYC analysis",
    },
    {
        "name": "transfer_statements",
        "tables": ["transfers", "statements"],
        "use_cases": "Transfer analytics, account statements, money flow",
    },
    {
        "name": "organization",
        "tables": ["branches", "employees"],
        "use_cases": "Branch analytics, employee management, organizational structure",
    },
    {
        "name": "refunds",
        "tables": ["refunds"],
        "use_cases": "Refund analysis, refund rate, refund reasons",
    },
    {
        "name": "audit",
        "tables": ["audit_logs"],
        "use_cases": "Audit trail, system activity tracking",
    },
]


def _format_table(table: dict) -> str:
    """Format a single table definition as readable text."""
    lines = [f"Table: {table['name']}"]
    lines.append(f"  Description: {table.get('description', '')}")
    lines.append("  Columns:")
    for col in table.get("columns", []):
        constraint = f" ({col['constraints']})" if col.get("constraints") else ""
        lines.append(f"    - {col['name']} ({col['type']}){constraint}: {col.get('description', '')}")

    rels = table.get("relationships", [])
    if rels:
        lines.append("  Relationships:")
        for rel in rels:
            lines.append(f"    - {rel['from']} -> {rel['to']} ({rel['type']})")
    return "\n".join(lines)


def create_chunks(schema_path: Path | str = _DEFAULT_SCHEMA_PATH) -> list[dict]:
    """Create domain-clustered schema chunks from schema.json.

    Returns a list of dicts with keys: id, text, metadata.
    """
    with open(schema_path, encoding="utf-8") as f:
        tables: list[dict] = json.load(f)

    table_map = {t["name"]: t for t in tables}

    chunks: list[dict] = []
    for cluster in CLUSTERS:
        parts = [f"Domain: {cluster['name']}"]
        parts.append(f"Use cases: {cluster['use_cases']}")
        parts.append("")

        cluster_tables = [table_map[name] for name in cluster["tables"] if name in table_map]
        for tbl in cluster_tables:
            parts.append(_format_table(tbl))
            parts.append("")

        chunks.append(
            {
                "id": f"cluster_{cluster['name']}",
                "text": "\n".join(parts).strip(),
                "metadata": {
                    "cluster": cluster["name"],
                    "tables": ",".join(cluster["tables"]),
                },
            }
        )

    return chunks
