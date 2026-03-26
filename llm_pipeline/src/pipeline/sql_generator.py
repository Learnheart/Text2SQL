"""SQL Generator [LLM] — The ONLY component that uses LLM in the pipeline.

Calls Claude API to generate SQL from:
- User question
- Context Package (schema chunks, examples, metrics, join hints, business rules)
- Error feedback (on retry)

Model selection:
- Default: Claude Sonnet 4.6 (fast, cost-effective for L1-L2 queries)
- Fallback: Claude Opus 4.6 (after 3 Sonnet failures, or for complex L3-L4 queries)
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

from src.config import settings
from src.llm.base import LLMProvider
from src.models.schemas import ContextPackage
from src.pipeline.state import PipelineState

if TYPE_CHECKING:
    from src.session_logger import SessionLogger

_PROMPT_PATH = Path(__file__).resolve().parents[2] / "config" / "prompts" / "sql_generator_prompt.txt"


def _load_prompt_template() -> str:
    with open(_PROMPT_PATH, encoding="utf-8") as f:
        return f.read()


def generate_sql(
    state: PipelineState,
    *,
    llm_provider: LLMProvider,
    session_log: SessionLogger | None = None,
) -> PipelineState:
    """Generate SQL using LLM from question + context package.

    Processing time target: ~1000ms.
    """
    question = state["question"]
    context: ContextPackage = state["context_package"]
    attempt = state.get("attempt", 1)
    error_feedback = state.get("error_feedback", "")

    if session_log:
        session_log.step(4, "SQL_GENERATOR", f"Generating SQL (attempt {attempt})")

    # Select model: use fallback after multiple failures
    model = settings.llm_model
    if attempt > settings.pipeline_max_retries and settings.llm_fallback_model:
        model = settings.llm_fallback_model
        if session_log:
            session_log.detail("SQL_GENERATOR", f"Switching to fallback model: {model}")

    # Build system prompt
    system_prompt = _build_system_prompt(context)

    # Build user message
    user_message = _build_user_message(question, error_feedback)

    if session_log:
        session_log.detail("SQL_GENERATOR", f"Calling {model} (temperature={settings.llm_temperature})")

    # Call LLM
    t0 = time.perf_counter()
    response = llm_provider.create(
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
        model=model,
        max_tokens=settings.llm_max_tokens,
        temperature=settings.llm_temperature,
    )
    llm_ms = int((time.perf_counter() - t0) * 1000)

    if session_log:
        session_log.detail(
            "SQL_GENERATOR",
            f"LLM response: {response.total_tokens} tokens, {llm_ms}ms",
        )

    # Extract SQL from response
    sql = _extract_sql(response.text or "")
    if not sql:
        if session_log:
            session_log.detail("SQL_GENERATOR", "WARNING: Could not extract SQL from response")
        # Use raw text as fallback (might still be valid SQL)
        sql = (response.text or "").strip()

    if session_log:
        session_log.detail("SQL_GENERATOR", f"Generated SQL: {sql[:120]}")

    return {
        **state,
        "generated_sql": sql,
        "generation_model": model,
        "generation_tokens": response.total_tokens,
        "total_tokens": state.get("total_tokens", 0) + response.total_tokens,
    }


def _build_system_prompt(context: ContextPackage) -> str:
    """Build the system prompt from template + context package."""
    template = _load_prompt_template()

    # Format schema context
    schema_context = "\n\n".join(context.schema_chunks) if context.schema_chunks else "No schema context available."

    # Format join hints
    join_hints = "\n".join(f"- {h}" for h in context.join_hints) if context.join_hints else "No join hints."

    # Format metrics
    from src.knowledge.semantic_layer import SemanticLayer
    metric_lines: list[str] = []
    for m in context.metrics:
        line = f"- {m.name}: {m.sql}"
        if m.filter:
            line += f" (WHERE {m.filter})"
        if m.description:
            line += f" — {m.description}"
        metric_lines.append(line)
    metric_definitions = "\n".join(metric_lines) if metric_lines else "No specific metrics matched."

    # Format business rules
    business_rules = "\n".join(f"- {r}" for r in context.business_rules) if context.business_rules else "No business rules."

    # Format examples
    example_lines: list[str] = []
    for i, ex in enumerate(context.examples, 1):
        example_lines.append(f"Example {i}:")
        example_lines.append(f"  Q: {ex.question}")
        example_lines.append(f"  SQL: {ex.sql}")
        example_lines.append("")
    few_shot_examples = "\n".join(example_lines) if example_lines else "No examples available."

    # Format sensitive columns
    sensitive_columns = ", ".join(context.sensitive_columns) if context.sensitive_columns else "none"

    return template.format(
        schema_context=schema_context,
        join_hints=join_hints,
        metric_definitions=metric_definitions,
        business_rules=business_rules,
        few_shot_examples=few_shot_examples,
        sensitive_columns=sensitive_columns,
    )


def _build_user_message(question: str, error_feedback: str) -> str:
    """Build the user message, including error feedback on retry."""
    if error_feedback:
        return (
            f"PREVIOUS ATTEMPT FAILED. Please fix the SQL based on the error below.\n\n"
            f"--- ERROR FEEDBACK ---\n{error_feedback}\n--- END FEEDBACK ---\n\n"
            f"Original question: {question}\n\n"
            f"Generate the corrected SQL query:"
        )

    return f"Question: {question}"


def _extract_sql(text: str) -> str | None:
    """Extract SQL from LLM response, looking for ```sql ... ``` blocks."""
    # Try to find SQL in code block
    pattern = r"```(?:sql)?\s*\n?(.*?)```"
    match = re.search(pattern, text, re.DOTALL | re.IGNORECASE)
    if match:
        sql = match.group(1).strip()
        if sql:
            return sql

    # Fallback: if text starts with SELECT or WITH, treat entire text as SQL
    text_stripped = text.strip()
    if text_stripped.upper().startswith(("SELECT", "WITH")):
        # Take everything up to the first empty line or end
        lines: list[str] = []
        for line in text_stripped.split("\n"):
            stripped = line.strip()
            if not stripped and lines:
                break
            if stripped:
                lines.append(line)
        return "\n".join(lines).strip() if lines else None

    return None
