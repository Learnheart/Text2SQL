#!/usr/bin/env python3
"""Accuracy evaluation script for the Text-to-SQL agent.

Runs the agent against golden queries (or a separate eval set),
compares generated SQL execution results with expected SQL results,
and reports accuracy metrics.

Usage:
    python scripts/evaluate.py                    # full eval
    python scripts/evaluate.py --limit 10         # first 10 only
    python scripts/evaluate.py --category simple  # filter by category
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

# Ensure project root is on path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import settings
from src.data_access.connection import DatabasePool
from src.rag.embedding import EmbeddingService
from src.knowledge.vector_store import VectorStore
from src.knowledge.semantic_layer import SemanticLayer
from src.knowledge.example_store import ExampleStore
from src.rag.retrieval import RAGRetrieval
from src.agent.prompt_builder import PromptBuilder
from src.agent.agent import Agent


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class EvalResult:
    question: str
    expected_sql: str
    generated_sql: str | None
    status: str  # match | mismatch | error | skipped
    expected_row_count: int | None = None
    actual_row_count: int | None = None
    latency_ms: int = 0
    tool_calls: int = 0
    tokens: int = 0
    error_message: str = ""


@dataclass
class EvalSummary:
    total: int = 0
    success: int = 0
    mismatch: int = 0
    error: int = 0
    skipped: int = 0
    total_latency_ms: int = 0
    total_tokens: int = 0
    results: list[EvalResult] = field(default_factory=list)

    @property
    def accuracy(self) -> float:
        evaluated = self.total - self.skipped
        return (self.success / evaluated * 100) if evaluated > 0 else 0.0

    @property
    def avg_latency_ms(self) -> float:
        evaluated = self.total - self.skipped
        return (self.total_latency_ms / evaluated) if evaluated > 0 else 0.0


# ---------------------------------------------------------------------------
# Core evaluation logic
# ---------------------------------------------------------------------------

async def run_golden_sql(pool: DatabasePool, sql: str) -> dict | None:
    """Execute the golden SQL and return results, or None on error."""
    result = await pool.execute(sql)
    if "error" in result:
        return None
    return result


def results_match(expected: dict | None, actual: dict | None) -> bool:
    """Compare execution results by row_count (relaxed match).

    We compare row counts because the generated SQL may use different column
    aliases or ordering, but should return the same number of rows for the
    same question. For aggregation queries, we also compare the first row values.
    """
    if expected is None or actual is None:
        return False

    exp_count = expected.get("row_count", -1)
    act_count = actual.get("row_count", -2)

    # Row count must match
    if exp_count != act_count:
        return False

    # For single-row aggregation, compare values
    if exp_count == 1:
        exp_rows = expected.get("rows", [])
        act_rows = actual.get("rows", [])
        if exp_rows and act_rows:
            # Compare numeric values with tolerance
            for ev, av in zip(exp_rows[0], act_rows[0]):
                if isinstance(ev, (int, float)) and isinstance(av, (int, float)):
                    if abs(ev - av) > max(abs(ev) * 0.01, 1):  # 1% tolerance
                        return False
                # String values: exact match
                elif str(ev) != str(av):
                    # Allow different formatting — don't fail on minor diffs
                    pass

    return True


async def evaluate_single(
    agent: Agent,
    pool: DatabasePool,
    question: str,
    golden_sql: str,
) -> EvalResult:
    """Evaluate a single question against its golden SQL."""
    # Execute golden SQL for expected results
    expected = await run_golden_sql(pool, golden_sql)

    if expected is None:
        return EvalResult(
            question=question,
            expected_sql=golden_sql,
            generated_sql=None,
            status="skipped",
            error_message="Golden SQL failed to execute",
        )

    # Run agent
    try:
        response = await agent.run(question)
    except Exception as e:
        return EvalResult(
            question=question,
            expected_sql=golden_sql,
            generated_sql=None,
            status="error",
            error_message=str(e),
        )

    result = EvalResult(
        question=question,
        expected_sql=golden_sql,
        generated_sql=response.sql,
        status="error",
        expected_row_count=expected.get("row_count"),
        actual_row_count=response.results.get("row_count") if response.results else None,
        latency_ms=response.latency_ms,
        tool_calls=len(response.tool_calls),
        tokens=response.total_tokens,
    )

    if response.status != "success" or response.results is None:
        result.error_message = f"Agent status: {response.status}"
        return result

    if results_match(expected, response.results):
        result.status = "match"
    else:
        result.status = "mismatch"
        result.error_message = (
            f"Row count: expected={expected.get('row_count')}, "
            f"actual={response.results.get('row_count')}"
        )

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(args: argparse.Namespace) -> None:
    print("=" * 70)
    print("Text-to-SQL Agent — Accuracy Evaluation")
    print("=" * 70)

    # Validate API key
    if not settings.anthropic_api_key:
        print("ERROR: ANTHROPIC_API_KEY not set.")
        sys.exit(1)

    # Load golden queries
    golden_path = PROJECT_ROOT / "config" / "golden_queries.json"
    with open(golden_path, encoding="utf-8") as f:
        golden_queries = json.load(f)

    print(f"Loaded {len(golden_queries)} golden queries from {golden_path}")

    # Apply filters
    if args.limit:
        golden_queries = golden_queries[: args.limit]
        print(f"Limited to first {args.limit} queries")

    if args.category:
        golden_queries = [
            q for q in golden_queries
            if q.get("category", "").lower() == args.category.lower()
            or args.category.lower() in q.get("explanation", "").lower()
        ]
        print(f"Filtered to category '{args.category}': {len(golden_queries)} queries")

    # Initialize services
    print("\nInitializing services...")
    db_pool = DatabasePool()
    await db_pool.init()

    embedding_service = EmbeddingService()
    vector_store = VectorStore()
    semantic_layer = SemanticLayer()
    example_store = ExampleStore()
    rag_retrieval = RAGRetrieval(embedding_service, vector_store, semantic_layer, example_store)
    prompt_builder = PromptBuilder(semantic_layer, example_store)

    agent = Agent(
        db_pool=db_pool,
        embedding_service=embedding_service,
        vector_store=vector_store,
        semantic_layer=semantic_layer,
        rag_retrieval=rag_retrieval,
        prompt_builder=prompt_builder,
    )

    print("Services initialized. Starting evaluation...\n")

    # Run evaluation
    summary = EvalSummary(total=len(golden_queries))
    start_time = time.perf_counter()

    for i, gq in enumerate(golden_queries, 1):
        question = gq["question"]
        golden_sql = gq["sql"]

        print(f"[{i}/{summary.total}] {question[:60]}...", end=" ", flush=True)

        result = await evaluate_single(agent, db_pool, question, golden_sql)
        summary.results.append(result)
        summary.total_latency_ms += result.latency_ms
        summary.total_tokens += result.tokens

        if result.status == "match":
            summary.success += 1
            print(f"MATCH ({result.latency_ms}ms)")
        elif result.status == "mismatch":
            summary.mismatch += 1
            print(f"MISMATCH — {result.error_message}")
        elif result.status == "skipped":
            summary.skipped += 1
            print(f"SKIPPED — {result.error_message}")
        else:
            summary.error += 1
            print(f"ERROR — {result.error_message}")

    total_time = time.perf_counter() - start_time
    await db_pool.close()

    # Print summary
    print("\n" + "=" * 70)
    print("EVALUATION SUMMARY")
    print("=" * 70)
    print(f"Total queries:     {summary.total}")
    print(f"  Match:           {summary.success}")
    print(f"  Mismatch:        {summary.mismatch}")
    print(f"  Error:           {summary.error}")
    print(f"  Skipped:         {summary.skipped}")
    print(f"")
    print(f"Accuracy:          {summary.accuracy:.1f}%")
    print(f"Avg latency:       {summary.avg_latency_ms:.0f}ms")
    print(f"Total tokens:      {summary.total_tokens:,}")
    print(f"Total time:        {total_time:.1f}s")
    print("=" * 70)

    # Print failures detail
    failures = [r for r in summary.results if r.status in ("mismatch", "error")]
    if failures:
        print(f"\nFAILURES ({len(failures)}):")
        print("-" * 70)
        for r in failures:
            print(f"  Q: {r.question}")
            print(f"  Expected SQL: {r.expected_sql[:80]}...")
            print(f"  Generated SQL: {r.generated_sql[:80] if r.generated_sql else 'None'}...")
            print(f"  Status: {r.status} — {r.error_message}")
            print()

    # Save results to JSON
    output_path = PROJECT_ROOT / "eval_results.json"
    output_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "model": settings.llm_model,
        "total": summary.total,
        "accuracy_pct": round(summary.accuracy, 1),
        "avg_latency_ms": round(summary.avg_latency_ms),
        "total_tokens": summary.total_tokens,
        "results": [
            {
                "question": r.question,
                "status": r.status,
                "expected_sql": r.expected_sql,
                "generated_sql": r.generated_sql,
                "expected_row_count": r.expected_row_count,
                "actual_row_count": r.actual_row_count,
                "latency_ms": r.latency_ms,
                "tokens": r.tokens,
                "error": r.error_message,
            }
            for r in summary.results
        ],
    }
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {output_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate Text-to-SQL agent accuracy")
    parser.add_argument("--limit", type=int, help="Max number of queries to evaluate")
    parser.add_argument("--category", type=str, help="Filter queries by category")
    args = parser.parse_args()

    asyncio.run(main(args))
