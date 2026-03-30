# Text-to-SQL Agent — BIRD Multi-Database Evaluation

A RAG-enhanced LLM agent that converts natural language questions into SQL queries, evaluated on the [BIRD-SQL benchmark](https://bird-bench.github.io/) across 70+ diverse databases.

## Architecture — Phase 1: RAG-Enhanced Single Agent (Pattern 2)

```
User Question + db_id
    |
    v
[REST API / Streamlit UI]
    |
    v
[Step 1] RAG Retrieval (deterministic, no LLM)
    |-- Vector search schema chunks (ChromaDB, filtered by db_id)
    |-- Vector search similar examples (BIRD train split, filtered by db_id)
    |-- Lookup evidence (BIRD domain hints)
    |
    v
[Step 2] Prompt Build
    |-- System prompt + schema + evidence + examples injected
    |-- SQLite syntax enforced
    |
    v
[Step 3] LLM Agent (tool use loop) — provider-agnostic
    |-- Tools: execute_sql (SQLite), search_schema, get_column_values
    |-- ReAct loop: reason -> act -> observe -> repeat
    |-- Supports: Claude, GPT-4o, Groq, Ollama, vLLM
    |
    v
[Step 4] Response
    |-- SQL generated (SQLite syntax)
    |-- Query results (rows/columns)
    |-- Natural language explanation
    |
    v
[Step 5] Evaluation (optional)
    |-- Compare generated SQL results vs BIRD ground truth
    |-- Execution accuracy metric
```

## Tech Stack

| Component | Technology |
|-----------|-----------|
| LLM | Multi-provider: Claude, GPT-4o, Groq, Ollama, vLLM (pluggable via config) |
| Embedding | SentenceTransformer (BAAI/bge-large-en-v1.5) |
| Vector DB | ChromaDB (persistent, per-db metadata filtering) |
| Database | SQLite (BIRD benchmark databases, read-only) |
| Dataset | BIRD-SQL (HuggingFace: xu3kev/BIRD-SQL-data-train) |
| API | FastAPI (async, WebSocket) |
| UI | Streamlit (POC, with database selector) |
| Language | Python 3.11+ |

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
│   ├── routes.py        # POST /api/query, GET /api/health
│   └── websocket.py
├── rag/                 # RAG retrieval pipeline
│   ├── retrieval.py     # Vector search + evidence lookup (db_id aware)
│   ├── embedding.py     # SentenceTransformer wrapper
│   └── chunking.py      # Dynamic schema chunking per database
├── knowledge/           # Knowledge stores
│   ├── vector_store.py    # ChromaDB wrapper (multi-db metadata)
│   ├── example_store.py   # BIRD train split examples
│   └── evidence_store.py  # BIRD evidence per question
├── tools/               # 3 agent tools
│   ├── execute_sql.py     # Safe SQL execution (SQLite, read-only, auto LIMIT)
│   ├── search_schema.py   # Vector search for schema info (per db_id)
│   └── get_column_values.py  # DISTINCT value enumeration (SQLite)
├── data_access/         # Database layer
│   ├── db_registry.py   # Database Registry: db_id -> SQLite path
│   └── audit.py         # Audit logging
├── evaluation/          # BIRD evaluation framework
│   ├── engine.py        # Execution accuracy evaluation
│   ├── splitter.py      # Train/test split with strict isolation
│   └── report.py        # Per-database and overall metrics
├── models/schemas.py    # Pydantic models
├── config.py            # Settings (env-based)
└── session_logger.py    # Per-session file logging

data/bird/               # BIRD benchmark data
├── databases/           # SQLite files (70+ databases)
│   ├── video_games/video_games.sqlite
│   ├── car_retails/car_retails.sqlite
│   └── ...
├── train.json           # Full BIRD dataset
├── train_split.json     # Few-shot subset (indexed into ChromaDB)
└── test_split.json      # Evaluation subset (NEVER indexed)

tests/                   # Unit + E2E tests
config/                  # Prompts, placeholder semantic layer
scripts/                 # Data pipeline, schema indexing, evaluation
ui/                      # Streamlit chat UI with database selector
```

## Quick Start

### Prerequisites

- Python 3.11+
- LLM API key (Anthropic, OpenAI, Groq, or local Ollama/vLLM)
- BIRD SQLite database files

### 1. Install dependencies

```bash
pip install -e ".[dev]"
pip install datasets   # HuggingFace datasets for BIRD
```

### 2. Download BIRD dataset

```bash
python -m scripts.download_bird
# Downloads: HuggingFace dataset + SQLite database files
# Creates: data/bird/databases/, data/bird/train.json
```

### 3. Split train/test + index schemas

```bash
# Split BIRD examples into train (~10%) / test (~90%) per database
# Index schema chunks + train examples into ChromaDB
python -m scripts.index_schema
```

### 4. Configure environment

Edit `.env`:
```env
# LLM Provider
LLM_PROVIDER=anthropic
LLM_API_KEY=sk-ant-your-key-here
LLM_MODEL=claude-sonnet-4-6

# BIRD Data
BIRD_DB_DIR=./data/bird/databases
BIRD_TRAIN_SPLIT=./data/bird/train_split.json
BIRD_TEST_SPLIT=./data/bird/test_split.json

EMBEDDING_MODEL=BAAI/bge-large-en-v1.5
CHROMA_PERSIST_DIR=./chroma_db
```

### 5. Run API server

```bash
uvicorn src.api.app:app --reload --port 8000
```

### 6. Use it

**Option A — curl:**
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many games per genre?", "db_id": "video_games"}'
```

**Option B — Streamlit UI:**
```bash
streamlit run ui/streamlit_app.py
# Select database from dropdown, then ask questions
```

### 7. Run evaluation

```bash
# Evaluate on BIRD test split (execution accuracy)
python -m scripts.evaluate --split test

# Evaluate on specific database
python -m scripts.evaluate --split test --db_id video_games

# Quick test on small subset
python -m scripts.evaluate --split test --limit 50
```

## Evaluation

### Execution Accuracy (EX)

The primary metric: does the generated SQL return the **same result set** as the BIRD ground truth SQL?

```
For each (question, db_id, ground_truth_sql) in test_split:
  1. Run question through agent pipeline → generated_sql
  2. Execute generated_sql on db_id.sqlite → generated_result
  3. Execute ground_truth_sql on db_id.sqlite → expected_result
  4. Match = (set(generated_result) == set(expected_result))
```

### Train/Test Isolation

**Critical rule**: Test questions are NEVER used as few-shot examples.

- Train split (~10%): Indexed into ChromaDB, used for few-shot retrieval
- Test split (~90%): Used ONLY for evaluation, never indexed

## Safety Features

- **Read-only enforcement**: SQLite opened with `?mode=ro`
- **DML blocking**: INSERT/UPDATE/DELETE/DROP/ALTER/TRUNCATE blocked at tool level
- **Auto LIMIT**: Queries without LIMIT get `LIMIT 1000` appended
- **SQL injection prevention**: Table/column names validated
- **Per-database isolation**: Each db_id routes to its own SQLite file

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/query` | Ask a question (requires `question` + `db_id`) |
| GET | `/api/health` | Health check |
| GET | `/api/databases` | List available databases |
| WS | `/ws/query` | WebSocket streaming |

### POST /api/query

**Request:**
```json
{
  "question": "How many games per genre?",
  "db_id": "video_games"
}
```

**Response:**
```json
{
  "status": "success",
  "db_id": "video_games",
  "sql": "SELECT g.genre_name, COUNT(*) AS cnt FROM game ga JOIN genre g ON ga.genre_id = g.id GROUP BY g.genre_name ORDER BY cnt DESC",
  "results": {
    "columns": ["genre_name", "cnt"],
    "rows": [["Action", 210], ["Sports", 180]],
    "row_count": 12
  },
  "explanation": "Action genre has the most games (210), followed by Sports (180)...",
  "metadata": {
    "latency_ms": 3200,
    "tool_calls": 1,
    "tokens": 950
  }
}
```

## Architecture Documentation

Detailed architecture docs: `docs/03_Technical_Assessment/pattern_2_rag_single_agent/`

| Doc | Content |
|-----|---------|
| `01_design_pattern.md` | RAG + ReAct + Tool-Augmented Agent pattern |
| `02_components.md` | All components across 5 layers + Pipeline & Eval |
| `03_architecture_flow.md` | Data flow, evaluation flow, pipeline flow |
| `04_sequence_diagrams.md` | 6 sequence diagrams (happy path, multi-tool, error, streaming, eval, pipeline) |
| `05_tech_stack.md` | SQLite, ChromaDB, Claude, HuggingFace Datasets |
