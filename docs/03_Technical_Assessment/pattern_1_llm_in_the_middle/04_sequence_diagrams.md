# Sequence Diagrams — LLM-in-the-middle Pipeline

### Các sequence diagram chi tiết cho mỗi luồng xử lý | Text-to-SQL Agent Platform (Banking/POS)

---

## MỤC LỤC

1. [Diagram 1: E2E Happy Path](#1-diagram-1-e2e-happy-path)
2. [Diagram 2: Self-Correction Flow (Validation Error)](#2-diagram-2-self-correction-flow-validation-error)
3. [Diagram 3: Self-Correction Flow (Runtime Error)](#3-diagram-3-self-correction-flow-runtime-error)
4. [Diagram 4: Router Rejection Flow](#4-diagram-4-router-rejection-flow)
5. [Diagram 5: Streaming Flow](#5-diagram-5-streaming-flow)
6. [Diagram 6: Knowledge Layer Boot](#6-diagram-6-knowledge-layer-boot)

---

## 1. DIAGRAM 1: E2E HAPPY PATH

Luồng đầy đủ từ câu hỏi người dùng đến kết quả trả về — trường hợp thành công, không cần retry.

```mermaid
sequenceDiagram
    participant U as User
    participant API as REST API
    participant RT as Router [code]
    participant SL as Schema Linker [code]
    participant VS as Vector Store
    participant SEM as Semantic Layer
    participant ES as Example Store
    participant SG as SQL Generator [LLM]
    participant CL as Claude API
    participant VL as Validator [code]
    participant EX as Executor [code]
    participant PG as PostgreSQL
    participant AL as Audit Logger
    participant IA as Insight Analyzer [LLM, optional]

    Note over U,IA: === PHASE 1: TIẾP NHẬN ===
    U->>API: POST /api/query<br/>{"question": "Tổng doanh thu tháng 1 năm 2025?"}
    API->>API: Auth check + Rate limit
    API->>RT: route(question)

    Note over U,IA: === PHASE 2: ROUTING (< 50ms) ===
    RT->>RT: Keyword matching: "tổng", "doanh thu", "tháng"<br/>→ Match SQL patterns
    RT->>RT: Confidence: 0.95
    RT-->>SL: RouterResult{intent: SQL, confidence: 0.95, query: "..."}

    Note over U,IA: === PHASE 3: CONTEXT ASSEMBLY (50-200ms) ===
    SL->>VS: vector_search(embed("tổng doanh thu tháng 1"), top_k=5)
    VS-->>SL: [chunk_sales, chunk_merchants, chunk_sales_items]

    SL->>SEM: lookup(keywords=["doanh thu", "tháng"])
    SEM-->>SL: {metrics: [{name: "tổng_doanh_thu",<br/>sql: "SUM(sales.amount) WHERE status='completed'"}],<br/>dimensions: [{name: "tháng",<br/>sql: "DATE_TRUNC('month', created_at)"}],<br/>enums: {status: [completed, pending, failed]},<br/>joins: [sales.merchant_id → merchants.id]}

    SL->>ES: find_similar(question, top_k=3)
    ES-->>SL: [{q: "Tổng doanh thu Q4?",<br/>sql: "SELECT SUM(amount) FROM sales WHERE..."}, ...]

    SL->>SL: Assemble Context Package
    SL-->>SG: ContextPackage{tables, joins, metrics,<br/>dimensions, examples, enums, sensitive_cols, rules}

    Note over U,IA: === PHASE 4: SQL GENERATION (500-2000ms) ===
    SG->>SG: Build prompt:<br/>system_prompt + context_package +<br/>user_question + few_shot_examples
    SG->>CL: POST /v1/messages<br/>{model: "claude-sonnet-4-6-20250514",<br/>messages: [prompt], max_tokens: 1024}
    CL-->>SG: "```sql\nSELECT SUM(amount) AS tong_doanh_thu\nFROM sales\nWHERE status = 'completed'\nAND DATE_TRUNC('month', created_at) = '2025-01-01'\n```"
    SG->>SG: Parse SQL from markdown code block
    SG-->>VL: GeneratorResult{sql: "SELECT SUM(amount)...",<br/>model: "sonnet-4.6", tokens: 180, latency_ms: 850}

    Note over U,IA: === PHASE 5: VALIDATION (< 100ms) ===
    VL->>VL: 1. Syntax check: sqlparse.parse() → OK
    VL->>VL: 2. DML check: SELECT only → OK
    VL->>VL: 3. Table check: sales exists → OK
    VL->>VL: 4. Column check: amount, status, created_at exist → OK
    VL->>VL: 5. Sensitive check: no sensitive columns → OK
    VL->>VL: 6. LIMIT check: missing → auto add LIMIT 1000
    VL-->>EX: ValidationResult{status: pass,<br/>modified_sql: "SELECT SUM(amount)... LIMIT 1000"}

    Note over U,IA: === PHASE 6: EXECUTION (100-5000ms) ===
    EX->>PG: Execute SQL (read-only, timeout=30s)<br/>SELECT SUM(amount) AS tong_doanh_thu<br/>FROM sales WHERE status='completed'<br/>AND DATE_TRUNC('month', created_at)='2025-01-01'<br/>LIMIT 1000
    PG-->>EX: [{tong_doanh_thu: 15000000000}]
    EX->>AL: Log{user, sql, time_ms: 120,<br/>rows: 1, status: success}
    EX-->>API: ExecutionResult{status: success,<br/>data: [{tong_doanh_thu: 15000000000}],<br/>columns: ["tong_doanh_thu"], row_count: 1}

    Note over U,IA: === PHASE 7 (TÙY CHỌN): INSIGHT ===
    opt Insight Analyzer enabled (Phase 2+)
        API->>IA: analyze(question, data)
        IA->>CL: Generate narrative
        CL-->>IA: "Tổng doanh thu tháng 1/2025 đạt 15 tỷ đồng..."
        IA-->>API: insight_text
    end

    Note over U,IA: === PHASE 8: RESPONSE ===
    API-->>U: 200 OK<br/>{status: "success",<br/>sql: "SELECT SUM(amount)...",<br/>data: [{tong_doanh_thu: 15000000000}],<br/>metadata: {time_ms: 1450, rows: 1,<br/>tables: ["sales"], retries: 0}}
```

---

## 2. DIAGRAM 2: SELF-CORRECTION FLOW (VALIDATION ERROR)

Khi Validator phát hiện SQL không hợp lệ → error feedback → Generator retry.

```mermaid
sequenceDiagram
    participant SL as Schema Linker
    participant SG as SQL Generator [LLM]
    participant CL as Claude API
    participant VL as Validator [code]
    participant SC as Self-Correction [code]

    Note over SL,SC: === ATTEMPT 1 ===
    SL-->>SG: ContextPackage (tables: sales, merchants)

    SG->>CL: Prompt + Context + Question<br/>"Top 5 merchant có doanh thu cao nhất?"
    CL-->>SG: "SELECT m.name, SUM(t.amount) as revenue<br/>FROM transaction t<br/>JOIN merchants m ON t.merchant_id = m.id<br/>GROUP BY m.name ORDER BY revenue DESC LIMIT 5"

    SG-->>VL: sql = "SELECT ... FROM transaction t ..."

    VL->>VL: 1. Syntax check → OK
    VL->>VL: 2. DML check → OK
    VL->>VL: 3. Table check → FAIL!<br/>Table 'transaction' does not exist

    VL-->>SC: ValidationResult{status: fail,<br/>errors: ["Table 'transaction' not found.<br/>Available tables: sales, sales_items,<br/>merchants, accounts, ..."]}

    Note over SL,SC: === SELF-CORRECTION: BUILD FEEDBACK ===
    SC->>SC: retry_count = 1 (< 3, tiếp tục)
    SC->>SC: Build feedback:<br/>- Original SQL<br/>- Error: table 'transaction' not found<br/>- Available tables list<br/>- Attempt 2/3

    Note over SL,SC: === ATTEMPT 2 ===
    SC-->>SG: ErrorFeedback{original_sql, error_msg,<br/>available_tables, attempt: 2}

    SG->>SG: Append feedback to prompt
    SG->>CL: Prompt + Context + Question +<br/>ErrorFeedback
    CL-->>SG: "SELECT m.name, SUM(s.amount) as revenue<br/>FROM sales s<br/>JOIN merchants m ON s.merchant_id = m.id<br/>WHERE s.status = 'completed'<br/>GROUP BY m.name ORDER BY revenue DESC LIMIT 5"

    SG-->>VL: sql = "SELECT ... FROM sales s ..."

    VL->>VL: 1. Syntax check → OK
    VL->>VL: 2. DML check → OK
    VL->>VL: 3. Table check → OK (sales, merchants)
    VL->>VL: 4. Column check → OK
    VL->>VL: 5. Sensitive check → OK
    VL->>VL: 6. LIMIT check → OK (có LIMIT 5)

    VL-->>SC: ValidationResult{status: pass}

    Note over SL,SC: === TIẾP TỤC PIPELINE ===
    SC-->>VL: Forward to Executor
```

---

## 3. DIAGRAM 3: SELF-CORRECTION FLOW (RUNTIME ERROR)

Khi Validator pass nhưng PostgreSQL trả về runtime error → feedback → retry.

```mermaid
sequenceDiagram
    participant SG as SQL Generator [LLM]
    participant CL as Claude API
    participant VL as Validator [code]
    participant EX as Executor [code]
    participant PG as PostgreSQL
    participant SC as Self-Correction [code]

    Note over SG,SC: === ATTEMPT 1 ===
    SG->>CL: Prompt + Context
    CL-->>SG: "SELECT merchant_category, COUNT(*)<br/>FROM sales s JOIN merchants m<br/>ON s.merchant_id = m.id<br/>GROUP BY merchant_category"

    SG-->>VL: sql
    VL->>VL: All 6 checks → PASS
    Note right of VL: Validator pass vì 'merchant_category'<br/>có thể là alias hợp lệ<br/>mà validator không bắt được

    VL-->>EX: ValidationResult{status: pass}

    EX->>PG: Execute SQL
    PG-->>EX: ERROR: column "merchant_category"<br/>does not exist<br/>HINT: Perhaps you meant "category"<br/>in table "merchants"

    EX-->>SC: ExecutionResult{status: error,<br/>error: 'column "merchant_category" does not exist',<br/>hint: 'Perhaps you meant "category"'}

    Note over SG,SC: === SELF-CORRECTION: BUILD FEEDBACK ===
    SC->>SC: retry_count = 1 (< 3, tiếp tục)
    SC->>SC: Build feedback:<br/>- Original SQL<br/>- Runtime error + PostgreSQL hint<br/>- merchants columns: [id, name, category, city, ...]<br/>- Attempt 2/3

    Note over SG,SC: === ATTEMPT 2 ===
    SC-->>SG: ErrorFeedback{original_sql,<br/>runtime_error, pg_hint, table_columns, attempt: 2}

    SG->>CL: Prompt + Context + ErrorFeedback
    CL-->>SG: "SELECT m.category, COUNT(*) as total<br/>FROM sales s JOIN merchants m<br/>ON s.merchant_id = m.id<br/>WHERE s.status = 'completed'<br/>GROUP BY m.category"

    SG-->>VL: sql (fixed)
    VL->>VL: All 6 checks → PASS
    VL-->>EX: ValidationResult{status: pass}

    EX->>PG: Execute SQL (fixed)
    PG-->>EX: [{category: "F&B", total: 1500},<br/>{category: "Retail", total: 1200}, ...]

    EX-->>SC: ExecutionResult{status: success, rows: 5}
    Note over SG,SC: === THÀNH CÔNG SAU 1 LẦN RETRY ===
```

---

## 4. DIAGRAM 4: ROUTER REJECTION FLOW

Khi Router phát hiện câu hỏi không phải SQL → trả lời trực tiếp, không đi qua pipeline.

```mermaid
sequenceDiagram
    participant U as User
    participant API as REST API
    participant RT as Router [code]

    Note over U,RT: === TRƯỜNG HỢP 1: CHITCHAT ===
    U->>API: POST /api/query<br/>{"question": "Xin chào, bạn là ai?"}
    API->>RT: route("Xin chào, bạn là ai?")
    RT->>RT: Keyword match: "xin chào" → chitchat pattern
    RT->>RT: Confidence: 0.99
    RT-->>API: RouterResult{intent: CHITCHAT,<br/>confidence: 0.99}
    API-->>U: 200 OK<br/>{status: "chitchat",<br/>message: "Xin chào! Tôi là Text-to-SQL Assistant,<br/>chuyên hỗ trợ truy vấn dữ liệu Banking/POS.<br/>Bạn có thể hỏi tôi về doanh thu, giao dịch,<br/>merchant, v.v.",<br/>suggestions: ["Tổng doanh thu hôm nay?",<br/>"Top 5 merchant?", "Số giao dịch tháng này?"]}

    Note over U,RT: === TRƯỜNG HỢP 2: OUT-OF-SCOPE ===
    U->>API: POST /api/query<br/>{"question": "Thời tiết Hà Nội hôm nay?"}
    API->>RT: route("Thời tiết Hà Nội hôm nay?")
    RT->>RT: Keyword check: không match SQL, chitchat, domain
    RT->>RT: Domain check: không chứa keyword Banking/POS
    RT->>RT: Confidence: 0.90
    RT-->>API: RouterResult{intent: OUT_OF_SCOPE,<br/>confidence: 0.90}
    API-->>U: 200 OK<br/>{status: "out_of_scope",<br/>message: "Xin lỗi, tôi chỉ có thể hỗ trợ các câu hỏi<br/>liên quan đến dữ liệu Banking/POS.<br/>Ví dụ: doanh thu, giao dịch, merchant, tài khoản.",<br/>suggestions: ["Tổng doanh thu tháng này?",<br/>"Merchant nào có nhiều giao dịch nhất?"]}

    Note over U,RT: === TRƯỜNG HỢP 3: CLARIFICATION ===
    U->>API: POST /api/query<br/>{"question": "giao dịch"}
    API->>RT: route("giao dịch")
    RT->>RT: Keyword check: "giao dịch" → domain keyword
    RT->>RT: Nhưng câu hỏi quá ngắn/mơ hồ
    RT->>RT: Confidence: 0.60
    RT-->>API: RouterResult{intent: CLARIFICATION,<br/>confidence: 0.60}
    API-->>U: 200 OK<br/>{status: "clarification",<br/>message: "Bạn muốn biết gì về giao dịch?<br/>Vui lòng cung cấp thêm chi tiết.",<br/>suggestions: ["Tổng số giao dịch hôm nay?",<br/>"Giao dịch lớn nhất tháng này?",<br/>"Danh sách giao dịch của merchant X?"]}

    Note over U,RT: Tất cả 3 trường hợp đều KHÔNG đi qua<br/>Schema Linker, Generator, Validator, Executor<br/>→ Response time < 100ms, không tốn LLM cost
```

---

## 5. DIAGRAM 5: STREAMING FLOW

Luồng streaming qua WebSocket — user thấy kết quả dần dần.

```mermaid
sequenceDiagram
    participant U as User (Browser)
    participant WS as WebSocket Server
    participant LG as LangGraph Orchestrator
    participant RT as Router
    participant SL as Schema Linker
    participant SG as SQL Generator
    participant CL as Claude API (streaming)
    participant VL as Validator
    participant EX as Executor
    participant PG as PostgreSQL
    participant IA as Insight Analyzer (optional)

    U->>WS: ws://host/ws/query
    WS-->>U: {"event": "connected"}

    U->>WS: {"question": "Top 10 merchant doanh thu cao nhất Q1?"}
    WS->>LG: Start pipeline

    Note over LG,RT: Router (không stream)
    LG->>RT: route(question)
    RT-->>LG: intent: SQL
    LG->>WS: {"event": "status", "step": "router",<br/>"data": "Intent: SQL (confidence: 0.93)"}
    WS->>U: {"event": "status", ...}

    Note over LG,SL: Schema Linker (không stream)
    LG->>SL: link(question)
    SL-->>LG: ContextPackage
    LG->>WS: {"event": "status", "step": "linker",<br/>"data": "Found: sales, merchants (2 tables, 1 join)"}
    WS->>U: {"event": "status", ...}

    Note over LG,CL: SQL Generator (STREAM từng token)
    LG->>SG: generate(context, question)
    SG->>CL: POST /v1/messages (stream: true)

    loop Mỗi token từ Claude API
        CL-->>SG: token: "SELECT"
        SG-->>LG: token
        LG->>WS: {"event": "sql_token", "data": "SELECT"}
        WS->>U: {"event": "sql_token", "data": "SELECT"}
        Note right of U: User thấy SQL hiện dần trên UI
    end

    CL-->>SG: [stream end]
    SG-->>LG: full_sql
    LG->>WS: {"event": "sql_complete",<br/>"data": "SELECT m.name, SUM(s.amount)..."}
    WS->>U: {"event": "sql_complete", ...}

    Note over LG,VL: Validator (không stream)
    LG->>VL: validate(sql)
    VL-->>LG: pass
    LG->>WS: {"event": "status", "step": "validator",<br/>"data": "SQL validated: all checks passed"}
    WS->>U: {"event": "status", ...}

    Note over LG,PG: Executor (không stream)
    LG->>EX: execute(sql)
    EX->>PG: SQL query
    PG-->>EX: result set (10 rows)
    EX-->>LG: ExecutionResult

    LG->>WS: {"event": "result",<br/>"data": {"rows": [...], "columns": [...],<br/>"row_count": 10, "time_ms": 350}}
    WS->>U: {"event": "result", ...}
    Note right of U: User thấy bảng kết quả

    opt Insight Analyzer enabled (Phase 2+)
        Note over LG,IA: Insight Analyzer (STREAM)
        LG->>IA: analyze(question, result)
        IA->>CL: Generate insight (stream: true)

        loop Mỗi token insight
            CL-->>IA: token
            IA-->>LG: token
            LG->>WS: {"event": "insight_token", "data": "Top 10"}
            WS->>U: {"event": "insight_token", "data": "Top 10"}
        end

        LG->>WS: {"event": "insight_complete",<br/>"data": "Top 10 merchant doanh thu cao nhất Q1..."}
        WS->>U: {"event": "insight_complete", ...}
    end

    LG->>WS: {"event": "complete",<br/>"data": {"total_time_ms": 2100, "retries": 0}}
    WS->>U: {"event": "complete", ...}
    Note right of U: UI hiển thị trạng thái hoàn tất
```

---

## 6. DIAGRAM 6: KNOWLEDGE LAYER BOOT

Quy trình khởi tạo hệ thống — chạy một lần khi startup.

```mermaid
sequenceDiagram
    participant SYS as System Startup
    participant CFG as Config Loader
    participant PG as PostgreSQL
    participant SEM as Semantic Layer
    participant EMB as Embedding Model (bge-m3)
    participant VS as Vector Store (pgvector)
    participant ES as Example Store
    participant CACHE as Redis Cache

    Note over SYS,CACHE: === GIAI ĐOẠN 1: LOAD SCHEMA (< 1s) ===

    SYS->>CFG: Load schema.json (nếu có)
    CFG-->>SYS: Raw schema config

    SYS->>PG: SELECT table_name, column_name,<br/>data_type, is_nullable, column_default<br/>FROM information_schema.columns<br/>WHERE table_schema = 'public'
    PG-->>SYS: 14 tables, 90+ columns metadata

    SYS->>PG: SELECT tc.table_name, kcu.column_name,<br/>ccu.table_name AS foreign_table,<br/>ccu.column_name AS foreign_column<br/>FROM information_schema.table_constraints tc<br/>JOIN information_schema.key_column_usage kcu ...<br/>JOIN information_schema.constraint_column_usage ccu ...<br/>WHERE tc.constraint_type = 'FOREIGN KEY'
    PG-->>SYS: 13 foreign key relationships

    SYS->>PG: SELECT tablename,<br/>pg_size_pretty(pg_total_relation_size(tablename::text))<br/>FROM pg_tables WHERE schemaname = 'public'
    PG-->>SYS: Table sizes (e.g., sales: 45MB)

    Note over SYS,CACHE: === GIAI ĐOẠN 2: LOAD SEMANTIC LAYER (< 200ms) ===

    SYS->>SEM: Load semantic_layer.yaml
    SEM-->>SYS: {metrics: 15+, dimensions: 10+,<br/>aliases: 50+, join_map: 13,<br/>sensitive_cols: 5, enums: 8,<br/>business_rules: 10+}

    SYS->>SYS: Merge INFORMATION_SCHEMA +<br/>Semantic Layer +<br/>FK relationships<br/>→ Complete Schema Model

    Note over SYS,CACHE: === GIAI ĐOẠN 3: GENERATE EMBEDDINGS (~3-5s) ===

    SYS->>SYS: Create schema chunks<br/>(cluster-based, KHÔNG per-table):<br/>- Chunk 1: sales + sales_items (giao dịch)<br/>- Chunk 2: merchants + merchant_categories<br/>- Chunk 3: accounts + transfers<br/>- Chunk 4: users + roles<br/>- ...

    loop Mỗi schema chunk
        SYS->>EMB: embed(chunk_text)
        EMB-->>SYS: vector (1024 dimensions)
    end

    SYS->>SYS: Also embed:<br/>- Metric descriptions<br/>- Dimension descriptions<br/>- Vietnamese aliases

    Note over SYS,CACHE: === GIAI ĐOẠN 4: STORE EMBEDDINGS (< 500ms) ===

    loop Mỗi embedding
        SYS->>VS: INSERT INTO schema_embeddings<br/>(id, chunk_text, embedding, metadata)<br/>ON CONFLICT (id) DO UPDATE
    end

    VS-->>SYS: Embeddings indexed (IVFFlat/HNSW)

    Note over SYS,CACHE: === GIAI ĐOẠN 5: LOAD EXAMPLES (< 300ms) ===

    SYS->>ES: Load golden_queries.json (40+ queries)
    ES-->>SYS: Golden queries loaded

    SYS->>ES: Load user_corrections (từ database)
    ES-->>SYS: User corrections loaded

    SYS->>ES: Load pattern_templates.json
    ES-->>SYS: SQL pattern templates loaded

    loop Mỗi example
        SYS->>EMB: embed(example.question)
        EMB-->>SYS: vector
        SYS->>ES: Index example with embedding
    end

    Note over SYS,CACHE: === GIAI ĐOẠN 6: WARM CACHE (< 300ms) ===

    SYS->>CACHE: SET schema_metadata (TTL=1h)
    SYS->>CACHE: SET table_list (TTL=1h)
    SYS->>CACHE: SET semantic_config (TTL=1h)
    SYS->>CACHE: SET frequent_embeddings (TTL=30m)

    Note over SYS,CACHE: === HOÀN TẤT ===
    SYS->>SYS: Knowledge Layer READY<br/>Tổng thời gian: ~5-8 giây<br/>- 14 tables indexed<br/>- 13 relationships mapped<br/>- 40+ examples loaded<br/>- Vector store populated<br/>- Cache warmed
```

---

## TÓM TẮT CÁC DIAGRAMS

| Diagram | Mục đích | Các actors chính | Thời gian |
|---------|---------|-------------------|----------|
| **1. E2E Happy Path** | Luồng hoàn chỉnh từ đầu đến cuối | Tất cả 13 components | ~1.5s |
| **2. Validation Error** | Xử lý khi SQL syntax/schema sai | Generator, Validator, Self-Correction | +1s mỗi retry |
| **3. Runtime Error** | Xử lý khi PostgreSQL trả lỗi | Generator, Executor, Self-Correction | +1s mỗi retry |
| **4. Router Rejection** | Xử lý chitchat/out-of-scope | User, API, Router | < 100ms |
| **5. Streaming** | Stream SQL + insight qua WebSocket | WebSocket, Generator, Insight | ~2-3s |
| **6. Knowledge Boot** | Khởi tạo knowledge layer | System, PostgreSQL, Embedding, Vector Store | ~5-8s (1 lần) |
