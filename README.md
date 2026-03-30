# Text-to-SQL Agent Platform — BIRD Benchmark Evaluation

Convert natural language questions into SQL queries using LLM agents, evaluated on the [BIRD-SQL benchmark](https://bird-bench.github.io/) (70+ databases, 9,430+ examples).

## Architecture Patterns

Each pattern is a self-contained project in its own folder, representing a different phase of development.

| Phase | Pattern | Folder | Database | Status |
|-------|---------|--------|----------|--------|
| Phase 1 (R&D) | RAG-Enhanced Single Agent | [`rag_single_agent/`](rag_single_agent/) | SQLite (BIRD) | Implemented |
| Phase 2 (POC) | LLM-in-the-middle Pipeline | `llm_pipeline/` | PostgreSQL | Planned |
| Phase 3 (Production) | Adaptive Router + Tiered Agents | `adaptive_router/` | PostgreSQL | Planned |

### Pattern 1 — RAG Single Agent (Phase 1)

Single LLM agent with 3 tools + RAG context injection. Evaluated on BIRD benchmark with execution accuracy.

```
Question + db_id → RAG Retrieval (per db_id) → LLM Agent (tool use loop) → SQL + Results
```

### Pattern 2 — LLM Pipeline (Phase 2)

Deterministic pipeline with LLM only at SQL generation step. More control, better accuracy. Migrates to PostgreSQL.

```
Question → Router → Schema Linker → SQL Generator (LLM) → Validator → Executor
```

### Pattern 3 — Adaptive Router (Phase 3)

Intent-based routing to specialized agents. Production-grade with caching and monitoring.

```
Question → Adaptive Router → [Simple Agent | Complex Agent | Analyst Agent] → Results
```

## Quick Start

```bash
cd rag_single_agent
cat README.md      # Setup instructions for Phase 1
```

## Architecture Documentation

Detailed design docs for all 3 patterns: [`docs/03_Technical_Assessment/`](docs/03_Technical_Assessment/)

## Tech Stack

- **LLM:** Multi-provider (Anthropic, OpenAI, Groq, Ollama, vLLM)
- **Database:** SQLite (BIRD evaluation) → PostgreSQL 18 (production)
- **Benchmark:** BIRD-SQL (9,430+ examples, 70+ databases)
- **Language:** Python 3.11+
- **API:** FastAPI
