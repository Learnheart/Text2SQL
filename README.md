# Text-to-SQL Agent Platform — Banking/POS

Convert natural language questions (Vietnamese/English) into SQL queries for Banking/POS databases using LLM agents.

## Architecture Patterns

Each pattern is a self-contained project in its own folder, representing a different phase of development.

| Phase | Pattern | Folder | Status |
|-------|---------|--------|--------|
| Phase 1 (R&D) | RAG-Enhanced Single Agent | [`rag_single_agent/`](rag_single_agent/) | Implemented |
| Phase 2 (POC) | LLM-in-the-middle Pipeline | `llm_pipeline/` | Planned |
| Phase 3 (Production) | Adaptive Router + Tiered Agents | `adaptive_router/` | Planned |

### Pattern 1 — RAG Single Agent (Phase 1)

Single Claude agent with 4 tools + RAG context injection. Simple, fast to build.

```
Question → RAG Retrieval → Claude Agent (tool use loop) → SQL + Results
```

### Pattern 2 — LLM Pipeline (Phase 2)

Deterministic pipeline with LLM only at SQL generation step. More control, better accuracy.

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

- **LLM:** Claude Sonnet 4.6 (Anthropic API)
- **Database:** PostgreSQL 18 + pgvector
- **Language:** Python 3.11+
- **API:** FastAPI
