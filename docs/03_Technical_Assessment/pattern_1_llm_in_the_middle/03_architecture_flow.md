# Luồng Architecture Tổng Thể — LLM-in-the-middle Pipeline

### Kiến trúc hệ thống và data flow chi tiết | Text-to-SQL Agent Platform (BIRD → Production)

---

## MỤC LỤC

1. [Sơ đồ Kiến trúc Tổng thể 5 Layers](#1-sơ-đồ-kiến-trúc-tổng-thể-5-layers)
2. [Tương tác giữa các Layers](#2-tương-tác-giữa-các-layers)
3. [Main Data Flow — Happy Path](#3-main-data-flow--happy-path)
4. [Self-Correction Loop Flow](#4-self-correction-loop-flow)
5. [Knowledge Layer Boot Process](#5-knowledge-layer-boot-process)
6. [Runtime Flow (Per Query)](#6-runtime-flow-per-query)
7. [Streaming Architecture](#7-streaming-architecture)

---

## 1. SƠ ĐỒ KIẾN TRÚC TỔNG THỂ 5 LAYERS

```mermaid
graph TB
    subgraph "LAYER 1 — PRESENTATION"
        direction LR
        REST["REST API<br/>/api/query<br/>★ Bắt buộc"]
        WSOCK["WebSocket<br/>ws://host/ws/query<br/>★ Bắt buộc"]
        CHATUI["Chat UI<br/>Streamlit → React<br/>Khuyến nghị"]
        CLISDK["CLI / SDK<br/>Tùy chọn"]
    end

    subgraph "LAYER 2 — PROCESSING PIPELINE"
        direction TB

        subgraph "Orchestrator"
            LG["LangGraph<br/>State Machine + Conditional Edges"]
        end

        subgraph "Pipeline Steps"
            direction LR
            RT["Router<br/>[code]<br/>Intent Classification"]
            SL["Schema Linker<br/>[code]<br/>Context Assembly"]
            SG["SQL Generator<br/>[LLM]<br/>Claude Sonnet/Opus"]
            VL["Validator<br/>[code]<br/>6-step Check"]
            EX["Executor<br/>[code]<br/>Run SQL"]
        end

        subgraph "Optional"
            IA["Insight Analyzer<br/>[LLM]<br/>Phase 2+"]
        end

        SCL["Self-Correction Loop<br/>[code] max 3 retries"]
    end

    subgraph "LAYER 3 — KNOWLEDGE"
        direction LR
        SEM["Semantic Layer<br/>Metrics, Dimensions<br/>Aliases, Rules"]
        VS["Vector Store<br/>pgvector<br/>Schema Embeddings"]
        ES["Example Store<br/>40+ Golden Queries<br/>User Corrections"]
    end

    subgraph "LAYER 4 — DATA ACCESS"
        direction LR
        CP["Connection Pool<br/>asyncpg<br/>min=2, max=10"]
        AL["Audit Logger<br/>Who, What, When<br/>Compliance + Eval Tracking"]
        CACHE["Redis Cache<br/>Query + Session"]
    end

    subgraph "LAYER 5 — DATA"
        direction LR
        PG["PostgreSQL 18<br/>+ pgvector<br/>14 bảng, 90+ cols"]
        RR["Read Replica<br/>Production only"]
    end

    %% Layer 1 → Layer 2
    REST --> LG
    WSOCK --> LG
    CHATUI --> REST
    CHATUI --> WSOCK
    CLISDK --> REST

    %% Orchestrator → Pipeline
    LG --> RT --> SL --> SG --> VL --> EX
    EX --> IA

    %% Self-Correction
    VL -.->|"fail"| SCL
    EX -.->|"fail"| SCL
    SCL -.->|"retry"| SG

    %% Layer 2 ↔ Layer 3
    SL <-->|"vector search"| VS
    SL <-->|"dict lookup"| SEM
    SL <-->|"few-shot"| ES
    SG <-->|"examples"| ES

    %% Layer 2 ↔ Layer 4
    EX --> CP
    EX --> AL
    SG --> CACHE
    SL --> CACHE

    %% Layer 4 ↔ Layer 5
    CP --> PG
    CP --> RR
    VS -.->|"stored in"| PG

    %% Layer 2 → External
    SG -->|"API call"| CLAUDE["Claude API<br/>Sonnet 4.6 / Opus 4.6"]

    style SG fill:#ff9800,stroke:#e65100,color:#fff
    style IA fill:#ff9800,stroke:#e65100,color:#fff
    style CLAUDE fill:#ff9800,stroke:#e65100,color:#fff
    style LG fill:#1976d2,stroke:#0d47a1,color:#fff
    style SCL fill:#9c27b0,stroke:#6a1b9a,color:#fff
```

---

## 2. TƯƠNG TÁC GIỮA CÁC LAYERS

### 2.1 Bốn luồng tương tác chính

```mermaid
graph LR
    subgraph "1. User → Presentation → Pipeline"
        U["User"] -->|"question"| P["Presentation<br/>Layer 1"]
        P -->|"request"| PP["Processing<br/>Pipeline<br/>Layer 2"]
    end

    subgraph "2. Pipeline ↔ Knowledge"
        PP2["Processing<br/>Pipeline"] <-->|"context<br/>retrieval"| K["Knowledge<br/>Layer 3"]
    end

    subgraph "3. Pipeline ↔ Data Access"
        PP3["Processing<br/>Pipeline"] <-->|"execute<br/>+ audit"| DA["Data Access<br/>Layer 4"]
    end

    subgraph "4. Data Access ↔ Data"
        DA2["Data Access<br/>Layer 4"] <-->|"SQL queries<br/>+ results"| D["Data<br/>Layer 5"]
    end
```

### 2.2 Chi tiết từng luồng

| Luồng | Từ → Đến | Dữ liệu truyền | Mục đích |
|-------|---------|---------------|---------|
| **1** | User → Presentation → Pipeline | UserQuery (string + options) | Nhận câu hỏi từ user |
| **2** | Pipeline → Knowledge | Query embedding, keyword | Lấy context (bảng, metrics, examples) |
| **2** | Knowledge → Pipeline | Context Package (tables, joins, metrics, examples) | Cung cấp thông tin cho LLM |
| **3** | Pipeline → Data Access | Validated SQL string | Thực thi query |
| **3** | Data Access → Pipeline | ExecutionResult (data, columns, row_count) | Trả kết quả |
| **3** | Pipeline → Data Access | AuditRecord | Ghi log cho compliance |
| **4** | Data Access → Data | SQL query qua connection pool | Đọc dữ liệu từ PostgreSQL |
| **4** | Data → Data Access | Result set | Trả kết quả về |

---

## 3. MAIN DATA FLOW — HAPPY PATH

### 3.1 Dữ liệu truyền giữa từng bước

```mermaid
graph TD
    Q["User Question<br/><i>'Tổng doanh thu tháng 1?'</i>"]

    Q -->|"string"| RT["Router"]
    RT -->|"RouterResult<br/>{intent: SQL, confidence: 0.95,<br/>query: 'Tổng doanh thu tháng 1?'}"| SL["Schema Linker"]

    SL -->|"ContextPackage<br/>{tables: [sales, merchants],<br/>joins: [...],<br/>metrics: [{tổng_doanh_thu: SUM(amount)}],<br/>examples: [2 golden queries],<br/>enums: {status: [...]},<br/>business_rules: [...]}"| SG["SQL Generator<br/>[LLM]"]

    SG -->|"GeneratorResult<br/>{sql: 'SELECT SUM(amount)...',<br/>model: 'sonnet-4.6',<br/>tokens: 245}"| VL["Validator"]

    VL -->|"ValidationResult<br/>{status: pass,<br/>modified_sql: '...LIMIT 1000',<br/>checks: {all: true}}"| EX["Executor"]

    EX -->|"ExecutionResult<br/>{status: success,<br/>data: [{total: 15000000000}],<br/>rows: 1,<br/>time_ms: 120}"| RS["Response Builder"]

    RS --> RESP["Final Response<br/>{status: success,<br/>sql: '...',<br/>data: [...],<br/>metadata: {...}}"]

    style SG fill:#ff9800,stroke:#e65100,color:#fff
    style RESP fill:#4caf50,stroke:#2e7d32,color:#fff
```

### 3.2 Data payload chi tiết tại mỗi bước

| Bước | Input | Output | Data Format |
|------|-------|--------|-------------|
| **Router** | `"Tổng doanh thu tháng 1?"` | `RouterResult` | `{intent: "sql", confidence: 0.95, query: str}` |
| **Schema Linker** | `RouterResult` + query tới Knowledge Layer | `ContextPackage` | `{tables: [], joins: [], metrics: [], examples: [], enums: {}, sensitive: [], rules: []}` |
| **SQL Generator** | `ContextPackage` + query tới Claude API | `GeneratorResult` | `{sql: str, model: str, tokens: int, latency_ms: int}` |
| **Validator** | `GeneratorResult.sql` + schema metadata | `ValidationResult` | `{status: pass/fail, checks: {}, errors: [], modified_sql: str}` |
| **Executor** | `ValidationResult.modified_sql` tới PostgreSQL | `ExecutionResult` | `{status: success/error, data: [], columns: [], row_count: int, time_ms: int}` |
| **Response Builder** | `ExecutionResult` + metadata | `FinalResponse` | `{status: str, sql: str, data: [], metadata: {}}` |

---

## 4. SELF-CORRECTION LOOP FLOW

### 4.1 Validation Error → Retry

```mermaid
graph TD
    SG["SQL Generator<br/>Attempt 1"] -->|"SQL: SELECT SUM(amount)<br/>FROM transaction<br/>WHERE month = 1"| VL1{"Validator"}

    VL1 -->|"FAIL: Table 'transaction'<br/>does not exist.<br/>Did you mean 'sales'?"| FB1["Error Feedback Builder"]

    FB1 -->|"Feedback:<br/>- Error: unknown table 'transaction'<br/>- Available tables: sales, merchants...<br/>- Original SQL<br/>- Attempt: 2/3"| SG2["SQL Generator<br/>Attempt 2"]

    SG2 -->|"SQL: SELECT SUM(amount)<br/>FROM sales<br/>WHERE EXTRACT(MONTH FROM created_at) = 1"| VL2{"Validator"}

    VL2 -->|"PASS<br/>+ Auto LIMIT 1000"| EX["Executor"]

    EX --> SUCCESS["Thành công"]

    style SG fill:#ff9800,stroke:#e65100,color:#fff
    style SG2 fill:#ff9800,stroke:#e65100,color:#fff
    style VL1 fill:#f44336,stroke:#b71c1c,color:#fff
    style VL2 fill:#4caf50,stroke:#2e7d32,color:#fff
    style SUCCESS fill:#4caf50,stroke:#2e7d32,color:#fff
```

### 4.2 Execution Error → Retry

```mermaid
graph TD
    SG["SQL Generator<br/>Attempt 1"] -->|"SQL output"| VL{"Validator"}

    VL -->|"PASS"| EX1{"Executor<br/>Attempt 1"}

    EX1 -->|"FAIL: ERROR: column<br/>'sales.transaction_date'<br/>does not exist"| FB["Error Feedback Builder"]

    FB -->|"Feedback:<br/>- Runtime error: column not found<br/>- Hint: use 'created_at' instead<br/>- Original SQL<br/>- Attempt: 2/3"| SG2["SQL Generator<br/>Attempt 2"]

    SG2 --> VL2{"Validator"} --> EX2{"Executor<br/>Attempt 2"}

    EX2 -->|"SUCCESS"| RESULT["Trả kết quả"]

    style SG fill:#ff9800,stroke:#e65100,color:#fff
    style SG2 fill:#ff9800,stroke:#e65100,color:#fff
    style EX1 fill:#f44336,stroke:#b71c1c,color:#fff
    style RESULT fill:#4caf50,stroke:#2e7d32,color:#fff
```

### 4.3 Max Retry Exceeded

```mermaid
graph TD
    A1["Attempt 1"] -->|"FAIL"| A2["Attempt 2"]
    A2 -->|"FAIL"| A3["Attempt 3"]
    A3 -->|"FAIL"| STOP["retry_count >= 3<br/>DỪNG LẠI"]

    STOP --> ERR["Trả lời user:<br/>'Xin lỗi, tôi không thể tạo<br/>SQL chính xác cho câu hỏi này.<br/>Vui lòng diễn đạt lại hoặc<br/>liên hệ admin.'"]

    STOP --> LOG["Log failure:<br/>question, 3 SQL attempts,<br/>3 error messages,<br/>→ để team review và thêm example"]

    style ERR fill:#f44336,stroke:#b71c1c,color:#fff
    style LOG fill:#ff9800,stroke:#e65100,color:#fff
```

---

## 5. KNOWLEDGE LAYER BOOT PROCESS

Đây là quy trình khởi tạo **một lần** khi hệ thống start. Mục đích: xây dựng Knowledge Layer từ schema thực tế.

### 5.1 Boot Flow

```mermaid
graph TD
    START["System Start"] --> S1["1. Parse schema.json<br/>Đọc file cấu hình schema<br/>(nếu có)"]

    S1 --> S2["2. Query INFORMATION_SCHEMA<br/>SELECT table_name, column_name,<br/>data_type, is_nullable<br/>FROM information_schema.columns<br/>WHERE table_schema = 'public'"]

    S2 --> S3["3. Detect Relationships<br/>Query pg_constraint<br/>để lấy foreign keys"]

    S3 --> S4["4. Load Semantic Layer<br/>Đọc config YAML/JSON:<br/>metrics, dimensions, aliases,<br/>enums, sensitive_cols, rules"]

    S4 --> S5["5. Merge Schema + Semantic<br/>Kết hợp thông tin từ<br/>INFORMATION_SCHEMA + Semantic Layer"]

    S5 --> S6["6. Create Schema Chunks<br/>Cluster-based chunking:<br/>nhóm bảng liên quan"]

    S6 --> S7["7. Generate Embeddings<br/>bge-m3 embed mỗi chunk<br/>(tables + descriptions + columns)"]

    S7 --> S8["8. Upsert to Vector Store<br/>INSERT INTO embeddings<br/>ON CONFLICT UPDATE"]

    S8 --> S9["9. Load Example Store<br/>Đọc golden queries,<br/>user corrections,<br/>pattern templates"]

    S9 --> S10["10. Warm-up Cache<br/>Cache schema metadata,<br/>frequent embeddings"]

    S10 --> READY["SYSTEM READY<br/>Sẵn sàng nhận queries"]

    style START fill:#1976d2,stroke:#0d47a1,color:#fff
    style READY fill:#4caf50,stroke:#2e7d32,color:#fff
```

### 5.2 Chi tiết từng bước boot

| Bước | Hành động | Input | Output | Thời gian ước tính |
|------|----------|-------|--------|-------------------|
| 1 | Parse schema.json | File config | Schema metadata | < 100ms |
| 2 | Query INFORMATION_SCHEMA | PostgreSQL connection | Table/column metadata | < 500ms |
| 3 | Detect Relationships | pg_constraint query | FK relationships | < 200ms |
| 4 | Load Semantic Layer | YAML/JSON config files | Metrics, dimensions, aliases | < 100ms |
| 5 | Merge Schema + Semantic | Steps 2-4 output | Merged schema | < 50ms |
| 6 | Create Schema Chunks | Merged schema | Clustered chunks | < 100ms |
| 7 | Generate Embeddings | Chunks + bge-m3 model | Embedding vectors | ~2-5s (14 bảng) |
| 8 | Upsert Vector Store | Embeddings | Indexed vectors in pgvector | < 500ms |
| 9 | Load Example Store | Golden queries + corrections | In-memory example index | < 200ms |
| 10 | Warm-up Cache | Schema + embeddings | Redis cache populated | < 300ms |
| **Tổng** | | | | **~5-8 giây** |

---

## 6. RUNTIME FLOW (PER QUERY)

### 6.1 Runtime Flow chi tiết

```mermaid
graph TD
    subgraph "Phase 1: Tiếp nhận (< 10ms)"
        REQ["User Request"] --> AUTH["Auth Check<br/>API Key / JWT"]
        AUTH --> RATE["Rate Limit Check<br/>10 req/min"]
        RATE --> PARSE["Parse Request<br/>Extract question + options"]
    end

    subgraph "Phase 2: Router (< 50ms)"
        PARSE --> CACHE_CHK{"Cache Hit?<br/>Exact match query<br/>trong Redis"}
        CACHE_CHK -->|"HIT"| CACHE_RET["Trả kết quả từ cache"]
        CACHE_CHK -->|"MISS"| ROUTER["Router<br/>Keyword + Regex"]
        ROUTER --> INTENT{"Intent?"}
        INTENT -->|"Chitchat"| CHAT_RESP["Trả lời mặc định"]
        INTENT -->|"Out-of-scope"| OOS_RESP["Từ chối lịch sự"]
        INTENT -->|"Clarification"| CLAR_RESP["Yêu cầu làm rõ"]
        INTENT -->|"SQL"| CONTINUE["Tiếp tục pipeline"]
    end

    subgraph "Phase 3: Context (50-200ms)"
        CONTINUE --> EMBED["Embed question<br/>bge-m3"]
        EMBED --> VSEARCH["Vector Search<br/>top-5 schema chunks"]
        VSEARCH --> DICT["Semantic Layer Lookup<br/>metrics, joins, enums"]
        DICT --> EXAMPLES["Example Search<br/>top-3 similar queries"]
        EXAMPLES --> CTX["Assemble Context Package"]
    end

    subgraph "Phase 4: Generation (500-2000ms)"
        CTX --> PROMPT["Build Prompt<br/>system + context + question + examples"]
        PROMPT --> LLM_CALL["Call Claude API<br/>Sonnet 4.6"]
        LLM_CALL --> PARSE_SQL["Parse SQL from response"]
    end

    subgraph "Phase 5: Validation (< 100ms)"
        PARSE_SQL --> VALIDATE["6-step Validation<br/>syntax, DML, tables, cols,<br/>sensitive, cost"]
        VALIDATE --> VAL_OK{"Pass?"}
        VAL_OK -->|"FAIL"| RETRY{"retry < 3?"}
        RETRY -->|"Yes"| PROMPT
        RETRY -->|"No"| FAIL_RESP["Trả lời lỗi"]
    end

    subgraph "Phase 6: Execution (100-5000ms)"
        VAL_OK -->|"PASS"| EXECUTE["Execute SQL<br/>PostgreSQL<br/>timeout=30s"]
        EXECUTE --> EXEC_OK{"Thành công?"}
        EXEC_OK -->|"FAIL"| RETRY2{"retry < 3?"}
        RETRY2 -->|"Yes"| PROMPT
        RETRY2 -->|"No"| FAIL_RESP
        EXEC_OK -->|"SUCCESS"| RESULT["Build Response"]
    end

    subgraph "Phase 7: Response (< 50ms)"
        RESULT --> AUDIT["Audit Log"]
        RESULT --> CACHE_SET["Cache Result<br/>TTL = 5 min"]
        RESULT --> RESPOND["Trả kết quả cho user"]
    end

    style LLM_CALL fill:#ff9800,stroke:#e65100,color:#fff
    style RESPOND fill:#4caf50,stroke:#2e7d32,color:#fff
    style FAIL_RESP fill:#f44336,stroke:#b71c1c,color:#fff
    style CACHE_RET fill:#4caf50,stroke:#2e7d32,color:#fff
```

### 6.2 Timeline ước tính (Happy Path, không retry)

| Phase | Thời gian | Tích lũy |
|-------|----------|-------------|
| 1. Tiếp nhận | ~10ms | 10ms |
| 2. Router | ~30ms | 40ms |
| 3. Context Assembly | ~150ms | 190ms |
| 4. SQL Generation (LLM) | ~1000ms | 1190ms |
| 5. Validation | ~50ms | 1240ms |
| 6. Execution | ~200ms | 1440ms |
| 7. Response | ~30ms | **1470ms** |
| **Tổng (Happy Path)** | | **~1.5 giây** |

| Trường hợp | Thời gian ước tính |
|-----------|-------------------|
| Cache hit | < 50ms |
| Happy path (không retry) | ~1.5s |
| 1 retry | ~2.5s |
| 2 retries | ~3.5s |
| 3 retries + fail | ~4.5s |
| Complex query (L3-L4, Opus fallback) | ~4-6s |

---

## 7. STREAMING ARCHITECTURE

### 7.1 Gì được stream vs không stream

| Component | Stream? | Lý do |
|-----------|---------|-------|
| Router | Không | Kết quả ngay lập tức (< 50ms) |
| Schema Linker | Không | Kết quả ngay lập tức (< 200ms) |
| **SQL Generator** | **Có** | LLM sinh SQL từng token → stream để user thấy SQL đang hình thành |
| Validator | Không | Kết quả ngay lập tức (< 100ms) |
| Executor | Không | Đợi kết quả từ PostgreSQL rồi trả 1 lần |
| **Insight Analyzer** | **Có** (Phase 2+) | LLM sinh narrative từng token → stream để user đọc dần |

### 7.2 Streaming Flow

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant WS as WebSocket Server
    participant P as Pipeline
    participant LLM as Claude API

    U->>WS: Connect ws://host/ws/query
    WS->>U: Connected

    U->>WS: {"question": "Tổng doanh thu Q1?"}
    WS->>P: Start pipeline

    Note over P: Router + Schema Linker (không stream)
    P->>WS: {"event": "status", "data": "Đang phân tích câu hỏi..."}

    Note over P: SQL Generator (STREAM)
    P->>LLM: Prompt (streaming=true)

    loop Mỗi token từ LLM
        LLM->>P: token
        P->>WS: {"event": "sql_token", "data": "SELECT"}
        WS->>U: {"event": "sql_token", "data": "SELECT"}
    end

    P->>WS: {"event": "sql_complete", "data": "SELECT SUM(amount)..."}
    WS->>U: {"event": "sql_complete"}

    Note over P: Validator (không stream)
    P->>WS: {"event": "status", "data": "Đang kiểm tra SQL..."}

    Note over P: Executor (không stream)
    P->>WS: {"event": "status", "data": "Đang chạy query..."}
    P->>WS: {"event": "result", "data": {"rows": [...]}}
    WS->>U: {"event": "result", "data": {"rows": [...]}}

    Note over P: Insight Analyzer - Phase 2+ (STREAM)
    loop Mỗi token insight
        LLM->>P: token
        P->>WS: {"event": "insight_token", "data": "Tổng doanh thu..."}
        WS->>U: {"event": "insight_token", "data": "Tổng doanh thu..."}
    end

    P->>WS: {"event": "complete", "data": {"total_time_ms": 1500}}
    WS->>U: {"event": "complete"}
```

### 7.3 WebSocket Event Types

| Event | Khi nào | Data |
|-------|---------|------|
| `status` | Các bước không stream (Router, Linker, Validator, Executor) | String mô tả trạng thái |
| `sql_token` | Mỗi token SQL từ LLM | SQL token string |
| `sql_complete` | SQL đã sinh xong | Full SQL string |
| `result` | Executor trả kết quả | `{rows: [], columns: [], row_count: int}` |
| `insight_token` | Mỗi token insight từ LLM (Phase 2+) | Insight text token |
| `complete` | Pipeline hoàn tất | `{total_time_ms: int}` |
| `error` | Bất kỳ lỗi nào | `{message: str, code: str}` |
| `retry` | Đang retry SQL generation | `{attempt: int, reason: str}` |

---

## 8. TÓM TẮT

Kiến trúc LLM-in-the-middle Pipeline có các đặc điểm:

- **5 layers rõ ràng**: Presentation → Processing → Knowledge → Data Access → Data
- **1 LLM call duy nhất** trong main flow (SQL Generator), còn lại là deterministic code
- **Self-correction loop** tự động sửa lỗi, tối đa 3 lần retry
- **Knowledge Layer boot 1 lần** (~5-8s), runtime per-query ~1.5s (happy path)
- **Streaming** cho 2 bước LLM (SQL Generation và Insight), các bước khác trả kết quả ngay
- **Audit trail đầy đủ** tại mỗi bước — phù hợp compliance và evaluation tracking
