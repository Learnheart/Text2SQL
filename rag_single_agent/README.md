# Text-to-SQL Agent Platform — Banking/POS

A RAG-enhanced LLM agent that converts natural language questions (Vietnamese/English) into SQL queries for Banking/POS databases.

## Architecture — Phase 1: RAG-Enhanced Single Agent (Pattern 2)

```
User Question (Vietnamese/English)
    |
    v
[REST API / Streamlit UI]
    |
    v
[Step 1] RAG Retrieval (deterministic, no LLM)
    |-- Vector search schema chunks (ChromaDB)
    |-- Vector search similar examples (few-shot)
    |-- Keyword match metric definitions
    |
    v
[Step 2] Prompt Build
    |-- System prompt + RAG context injected
    |
    v
[Step 3] LLM Agent (tool use loop) — provider-agnostic
    |-- Tools: execute_sql, search_schema, get_metric, get_column_values
    |-- ReAct loop: reason -> act -> observe -> repeat
    |-- Supports: Claude, GPT-4o, Groq, Ollama, vLLM
    |
    v
[Step 4] Response
    |-- SQL generated
    |-- Query results (rows/columns)
    |-- Natural language explanation
    |
    v
[Step 5] Audit Logging (compliance)
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Multi-provider: Claude, GPT-4o, Groq, Ollama, vLLM (pluggable via config) |
| Embedding | SentenceTransformer (BAAI/bge-large-en-v1.5) |
| Vector DB | ChromaDB (persistent) |
| Database | PostgreSQL 18 + pgvector |
| API | FastAPI (async, WebSocket) |
| UI | Streamlit (POC) |
| Language | Python 3.11+ |

### Supported LLM Providers

| Provider | `LLM_PROVIDER` | `LLM_BASE_URL` | Tool Use |
|----------|----------------|-----------------|----------|
| Anthropic (Claude) | `anthropic` | — | Native |
| OpenAI (GPT-4o) | `openai` | — | Native |
| Groq (Llama 3) | `openai` | `https://api.groq.com/openai/v1` | Native |
| Ollama (local) | `openai` | `http://localhost:11434/v1` | Model-dependent |
| vLLM (self-hosted) | `openai` | `http://localhost:8000/v1` | Model-dependent |

## Project Structure

```
src/
├── agent/               # LLM agent with tool use loop
│   ├── agent.py         # Core agent: RAG -> prompt -> LLM loop -> response
│   ├── prompt_builder.py
│   └── response_parser.py
├── llm/                 # LLM provider abstraction (Strategy pattern)
│   ├── base.py          # LLMProvider ABC, LLMResponse, ToolCall
│   ├── anthropic_provider.py    # Anthropic Claude
│   ├── openai_compatible_provider.py  # OpenAI / Groq / Ollama / vLLM
│   └── factory.py       # Factory: config -> provider instance
├── api/                 # REST API + WebSocket
│   ├── app.py           # FastAPI with lifespan
│   ├── routes.py        # POST /api/query, GET /api/health, POST /api/feedback
│   └── websocket.py
├── rag/                 # RAG retrieval pipeline
│   ├── retrieval.py     # Vector search + metric matching
│   ├── embedding.py     # SentenceTransformer wrapper
│   └── chunking.py      # Domain-clustered schema chunking (7 clusters)
├── knowledge/           # Semantic metadata
│   ├── semantic_layer.py  # 15+ metrics, aliases, sensitive columns
│   ├── vector_store.py    # ChromaDB wrapper
│   └── example_store.py   # 40+ golden queries
├── tools/               # 4 agent tools
│   ├── execute_sql.py     # Safe SQL execution (read-only, DML blocking, auto LIMIT)
│   ├── search_schema.py   # Vector search for schema info
│   ├── get_metric.py      # Business metric lookup
│   └── get_column_values.py  # DISTINCT value enumeration
├── data_access/         # Database layer
│   ├── connection.py    # Async PostgreSQL pool (read-only enforced)
│   └── audit.py         # Compliance audit logging
├── models/schemas.py    # Pydantic models
├── config.py            # Settings (env-based)
└── session_logger.py    # Per-session file logging for tracing

tests/                   # 92 tests (unit + E2E)
config/                  # Semantic layer YAML, golden queries JSON, prompts
data/                    # Schema metadata, sample queries
ui/                      # Streamlit chat UI
scripts/                 # DB init, schema indexing, evaluation
docker/                  # PostgreSQL + pgvector
```

## Quick Start

### Prerequisites

- Python 3.11+
- Docker Desktop (for PostgreSQL)
- LLM API key (Anthropic, OpenAI, Groq, or local Ollama/vLLM)

### 1. Install dependencies

```bash
pip install -e ".[dev]"
pip install psycopg2-binary faker
```

### 2. Start PostgreSQL

```bash
cd docker
docker compose up -d
```

### 3. Configure environment

Edit `.env` — choose your LLM provider:
```env
DB_HOST=localhost
DB_PORT=5432
DB_NAME=test_db
DB_USER=test_db_user
DB_PASSWORD=test_db_password

# Option 1: Anthropic Claude (default)
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-key-here
LLM_MODEL=claude-sonnet-4-6

# Option 2: Groq (fast, free tier available)
# LLM_PROVIDER=openai
# LLM_API_KEY=gsk_your_groq_key
# LLM_BASE_URL=https://api.groq.com/openai/v1
# LLM_MODEL=llama-3.3-70b-versatile

# Option 3: Ollama (local, free)
# LLM_PROVIDER=openai
# LLM_API_KEY=ollama
# LLM_BASE_URL=http://localhost:11434/v1
# LLM_MODEL=llama3.1

EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
CHROMA_PERSIST_DIR=./chroma_db
```

### 4. Generate sample data + init DB

```bash
# Create tables and seed Banking/POS data
python gen_data.py

# Create audit tables + read-only role
psql -h localhost -U test_db_user -d test_db -f scripts/init_db.sql
```

### 5. Index schema into ChromaDB

```bash
python -m scripts.index_schema
```

### 6. Run API server

```bash
uvicorn src.api.app:app --reload --port 8000
```

### 7. Use it

**Option A — curl:**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "Tong doanh thu thang 3?"}'
```

**Option B — Streamlit UI:**
```bash
streamlit run ui/streamlit_app.py
```

**Option C — Health check:**
```bash
curl http://localhost:8000/api/health
```

## Running Tests

```bash
# Unit tests (no external dependencies needed)
pytest tests/ -v

# E2E tests (requires running PostgreSQL + Anthropic API key)
pytest tests/test_e2e.py -v
```

## Session Logging

Each API request creates a separate log file in `logs/` for tracing:

```
logs/session_a1b2c3d4e5f6_20260326_103001.log
```

Example log output:
```
================================================================================
SESSION: a1b2c3d4e5f6
TIME:    2026-03-26 10:30:01.123
QUESTION: Tong doanh thu thang 3?
================================================================================
[2026-03-26 10:30:01.123] [STEP 1/5] [RAG_RETRIEVAL] Retrieving context...
[2026-03-26 10:30:01.130] [STEP 1/5] [RAG_RETRIEVAL] Question embedded, dim=1024 (7ms)
[2026-03-26 10:30:01.155] [STEP 1/5] [RAG_RETRIEVAL] Schema vector search: 5 chunks (25ms)
[2026-03-26 10:30:01.170] [STEP 1/5] [RAG_RETRIEVAL] Example vector search: 3 examples (15ms)
[2026-03-26 10:30:01.172] [STEP 1/5] [RAG_RETRIEVAL] Metric keyword match: ['doanh_thu'] (2ms)
[2026-03-26 10:30:01.174] [STEP 2/5] [PROMPT_BUILD] System prompt length: 2048 chars (1ms)
[2026-03-26 10:30:02.500] [STEP 3/5] [LLM_CALL] Iteration 1: stop_reason=tool_use, tokens=850 (1324ms)
[2026-03-26 10:30:02.501] [STEP 3/5] [TOOL_DISPATCH] execute_sql -> input: {"sql": "SELECT SUM..."}
[2026-03-26 10:30:02.800] [STEP 3/5] [TOOL_RESULT] execute_sql -> 1 rows, 299ms (299ms)
[2026-03-26 10:30:03.100] [STEP 3/5] [LLM_CALL] Iteration 2: stop_reason=end_turn, tokens=200 (300ms)
[2026-03-26 10:30:03.101] [STEP 4/5] [RESPONSE] status=success, sql=yes
[2026-03-26 10:30:03.102] [STEP 5/5] [COMPLETE] status=success, tokens=1050, tool_calls=1 (total: 1979ms)
================================================================================
```

## Safety Features

- **Read-only enforcement**: Connection pool sets `default_transaction_read_only = on`
- **DML blocking**: INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE blocked at tool level
- **Auto LIMIT**: Queries without LIMIT get `LIMIT 1000` appended
- **Sensitive column blocking**: CVV, card_number, DOB, email columns cannot be enumerated
- **SQL injection prevention**: Table/column names validated (alphanumeric + underscore only)
- **Statement timeout**: 30s default to prevent long-running queries
- **Audit logging**: Every query logged for Banking compliance

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/query` | Ask a question, get SQL + results + explanation |
| GET | `/api/health` | Health check |
| POST | `/api/feedback` | Submit correction for wrong SQL |
| WS | `/ws/query` | WebSocket streaming |

### POST /api/query

**Request:**
```json
{
  "question": "Tong doanh thu thang 3?"
}
```

**Response:**
```json
{
  "status": "success",
  "sql": "SELECT SUM(total_amount) FROM sales WHERE created_at >= '2026-03-01'",
  "results": {
    "columns": ["sum"],
    "rows": [[1500000.00]],
    "row_count": 1
  },
  "explanation": "Tong doanh thu thang 3 la 1,500,000 VND",
  "metadata": {
    "latency_ms": 1979,
    "tool_calls": 1,
    "tokens": 1050
  }
}
```

## Architecture Documentation

Detailed architecture docs are in `docs/03_Technical_Assessment/`:

| Phase | Pattern | Status |
|-------|---------|--------|
| Phase 1 (R&D) | RAG-Enhanced Single Agent | **Implemented** |
| Phase 2 (POC) | LLM-in-the-middle Pipeline | Planned |
| Phase 3 (Production) | Adaptive Router + Tiered Agents | Planned |
