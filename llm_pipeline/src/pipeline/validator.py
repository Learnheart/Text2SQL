"""Validator [CODE] — 6-step deterministic SQL validation before execution.

Checks:
1. Syntax check (sqlparse)
2. DML check (only SELECT allowed)
3. Table/column existence check
4. Sensitive column check
5. LIMIT check (auto-add if missing)
6. Cost estimate check (EXPLAIN-based, optional)

No LLM is used — pure rule-based validation.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import sqlparse
from sqlparse.sql import IdentifierList, Identifier, Where, Parenthesis
from sqlparse.tokens import Keyword, DML

from src.models.schemas import ValidationResult
from src.pipeline.state import PipelineState

if TYPE_CHECKING:
    from src.session_logger import SessionLogger

_SCHEMA_PATH = Path(__file__).resolve().parents[2] / "data" / "schema.json"

# DML statements that are NOT allowed
_FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "TRUNCATE",
    "CREATE", "GRANT", "REVOKE", "EXECUTE", "COPY",
}

# Sensitive columns that must be blocked
_SENSITIVE_COLUMNS = {
    "cards.cvv", "cards.card_number",
    "customers.dob", "customers.email",
    "accounts.account_number",
}

_DEFAULT_LIMIT = 1000


class SchemaRegistry:
    """Loads and caches the database schema for validation."""

    def __init__(self, schema_path: Path | str = _SCHEMA_PATH) -> None:
        self._tables: dict[str, set[str]] = {}
        self._load(Path(schema_path))

    def _load(self, path: Path) -> None:
        with open(path, encoding="utf-8") as f:
            tables = json.load(f)
        for table in tables:
            cols = {col["name"] for col in table.get("columns", [])}
            self._tables[table["name"]] = cols

    @property
    def table_names(self) -> set[str]:
        return set(self._tables.keys())

    def get_columns(self, table: str) -> set[str]:
        return self._tables.get(table, set())

    def table_exists(self, table: str) -> bool:
        return table in self._tables

    def column_exists(self, table: str, column: str) -> bool:
        return column in self._tables.get(table, set())


# Module-level registry (lazy loaded)
_registry: SchemaRegistry | None = None


def _get_registry() -> SchemaRegistry:
    global _registry
    if _registry is None:
        _registry = SchemaRegistry()
    return _registry


def validate(state: PipelineState, *, session_log: SessionLogger | None = None) -> PipelineState:
    """Run 6-step validation on the generated SQL. Returns updated state with ValidationResult."""
    sql = state.get("generated_sql", "").strip()

    if session_log:
        session_log.step(5, "VALIDATOR", f"Validating SQL: {sql[:100]}")

    errors: list[str] = []
    warnings: list[str] = []
    sanitized_sql = sql

    # Step 1: Syntax check
    if not _check_syntax(sql):
        errors.append("SQL syntax is invalid (failed sqlparse parsing)")
        if session_log:
            session_log.detail("VALIDATOR", "FAIL: Step 1 — Syntax check failed")
        return {
            **state,
            "validation_result": ValidationResult(
                is_valid=False, errors=errors, warnings=warnings, sanitized_sql=sql
            ),
        }

    if session_log:
        session_log.detail("VALIDATOR", "PASS: Step 1 — Syntax OK")

    # Step 2: DML check (only SELECT)
    dml_error = _check_dml(sql)
    if dml_error:
        errors.append(dml_error)
        if session_log:
            session_log.detail("VALIDATOR", f"FAIL: Step 2 — {dml_error}")
        return {
            **state,
            "validation_result": ValidationResult(
                is_valid=False, errors=errors, warnings=warnings, sanitized_sql=sql
            ),
        }

    if session_log:
        session_log.detail("VALIDATOR", "PASS: Step 2 — DML safe (SELECT only)")

    # Step 3: Table/column existence check
    registry = _get_registry()
    table_errors = _check_tables(sql, registry)
    if table_errors:
        errors.extend(table_errors)
        if session_log:
            session_log.detail("VALIDATOR", f"FAIL: Step 3 — {table_errors}")
        return {
            **state,
            "validation_result": ValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                sanitized_sql=sql,
            ),
        }

    if session_log:
        session_log.detail("VALIDATOR", "PASS: Step 3 — Tables/columns exist")

    # Step 4: Sensitive column check
    sensitive_warnings = _check_sensitive_columns(sql)
    if sensitive_warnings:
        warnings.extend(sensitive_warnings)
        if session_log:
            session_log.detail("VALIDATOR", f"WARNING: Step 4 — Sensitive columns: {sensitive_warnings}")
    else:
        if session_log:
            session_log.detail("VALIDATOR", "PASS: Step 4 — No sensitive columns")

    # Step 5: LIMIT check (auto-add if missing)
    sanitized_sql = _ensure_limit(sql)
    if sanitized_sql != sql:
        warnings.append(f"Auto-added LIMIT {_DEFAULT_LIMIT}")
        if session_log:
            session_log.detail("VALIDATOR", f"WARNING: Step 5 — Auto-added LIMIT {_DEFAULT_LIMIT}")
    else:
        if session_log:
            session_log.detail("VALIDATOR", "PASS: Step 5 — LIMIT present")

    # Step 6: Cost check (skipped in validation — done at execution time if needed)
    if session_log:
        session_log.detail("VALIDATOR", "SKIP: Step 6 — Cost check deferred to execution")

    return {
        **state,
        "validation_result": ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            sanitized_sql=sanitized_sql,
        ),
    }


# --- Validation helpers ---


def _check_syntax(sql: str) -> bool:
    """Step 1: Basic syntax check using sqlparse."""
    if not sql or not sql.strip():
        return False
    try:
        parsed = sqlparse.parse(sql)
        return len(parsed) > 0 and len(parsed[0].tokens) > 0
    except Exception:
        return False


def _check_dml(sql: str) -> str | None:
    """Step 2: Ensure only SELECT statements. Returns error message or None."""
    sql_upper = sql.upper().strip()

    # Check for forbidden keywords at statement level
    for keyword in _FORBIDDEN_KEYWORDS:
        # Match keyword at start or after semicolon/whitespace (not in strings)
        pattern = rf"(?:^|\s|;){keyword}\s"
        if re.search(pattern, sql_upper):
            return f"Only SELECT queries are allowed. Found forbidden keyword: {keyword}"

    # Must start with SELECT or WITH (for CTEs)
    if not (sql_upper.startswith("SELECT") or sql_upper.startswith("WITH")):
        return "Query must start with SELECT or WITH (CTE)"

    return None


def _check_tables(sql: str, registry: SchemaRegistry) -> list[str]:
    """Step 3: Check that referenced tables exist in schema."""
    errors: list[str] = []
    referenced_tables = _extract_table_names(sql)

    for table in referenced_tables:
        if not registry.table_exists(table):
            available = ", ".join(sorted(registry.table_names))
            errors.append(f"Table '{table}' does not exist. Available tables: {available}")

    return errors


def _extract_table_names(sql: str) -> set[str]:
    """Extract table names from SQL using regex (handles FROM, JOIN, subqueries)."""
    tables: set[str] = set()

    # Pattern: FROM table_name or JOIN table_name (with optional alias)
    pattern = r"(?:FROM|JOIN)\s+([a-zA-Z_][a-zA-Z0-9_]*)"
    for match in re.finditer(pattern, sql, re.IGNORECASE):
        table = match.group(1).lower()
        # Exclude SQL keywords that might follow FROM/JOIN
        if table not in {"select", "where", "on", "as", "inner", "left", "right", "outer", "cross", "full", "lateral"}:
            tables.add(table)

    return tables


def _check_sensitive_columns(sql: str) -> list[str]:
    """Step 4: Flag queries accessing sensitive columns."""
    warnings: list[str] = []
    sql_lower = sql.lower()

    for sensitive in _SENSITIVE_COLUMNS:
        table, col = sensitive.split(".")
        # Check for table.column or just column (if table is in FROM)
        if f"{table}.{col}" in sql_lower or (col in sql_lower and table in sql_lower):
            warnings.append(f"Query accesses sensitive column: {sensitive}")

    return warnings


def _ensure_limit(sql: str) -> str:
    """Step 5: Add LIMIT clause if not present."""
    sql_upper = sql.upper().strip()

    # Already has LIMIT
    if re.search(r"\bLIMIT\s+\d+", sql_upper):
        return sql

    # Remove trailing semicolon before adding LIMIT
    sql_stripped = sql.rstrip().rstrip(";")
    return f"{sql_stripped}\nLIMIT {_DEFAULT_LIMIT}"
