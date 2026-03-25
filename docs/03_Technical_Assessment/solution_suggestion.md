# SOLUTION SUGGESTION: Text-to-SQL Agent Platform

### Đề xuất Giải pháp Kỹ thuật | v1.0

---

## MỤC LỤC

1. [Hướng tiếp cận (Approach)](#1-hướng-tiếp-cận-approach)
2. [Các Component/Layer bắt buộc](#2-các-componentlayer-bắt-buộc)
3. [Ước lượng bài toán & Capacity Planning](#3-ước-lượng-bài-toán--capacity-planning)
4. [Top 3 Design Patterns phù hợp](#4-top-3-design-patterns-phù-hợp)
5. [Đề xuất Tech Stack](#5-đề-xuất-tech-stack)
6. [Phân tích Scale-up](#6-phân-tích-scale-up)
7. [Schema Linker — Cơ chế phát hiện Relationship](#7-schema-linker--cơ-chế-phát-hiện-relationship)
8. [Pipeline Communication & Hallucination](#8-pipeline-communication--hallucination)
9. [Phân tích mức độ phụ thuộc LLM theo Pattern](#9-phân-tích-mức-độ-phụ-thuộc-llm-theo-pattern)
10. [Semantic Layer — Yêu cầu chi tiết](#10-semantic-layer--yêu-cầu-chi-tiết)

---

## 1. HƯỚNG TIẾP CẬN (APPROACH)

### 1.1 Tóm tắt bài toán

Xây dựng một **AI Agent** cho phép người dùng nghiệp vụ (không biết SQL) đặt câu hỏi bằng ngôn ngữ tự nhiên (tiếng Việt/Anh) và nhận câu trả lời chính xác từ database PostgreSQL trong domain **Banking/POS**.

**Quy mô dữ liệu hiện tại:**

| Đặc điểm | Giá trị |
|-----------|---------|
| Số bảng | 14 |
| Số columns | 90+ |
| Record lớn nhất (sales) | 200,000+ rows |
| Tổng relationships (FK) | 13 |
| Độ phức tạp JOIN tối đa | 4 bảng (self-transfer detection) |
| Ngôn ngữ input | Tiếng Việt + Tiếng Anh |

### 1.2 Approach được đề xuất: **LLM-in-the-middle Pipeline**

Sau khi phân tích các approach phổ biến trên thị trường, approach được đề xuất là **LLM-in-the-middle Pipeline** — một pipeline mà LLM chỉ đảm nhận đúng 1 bước (sinh SQL), còn lại tất cả đều là deterministic code:

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   User Question ──→ [Retrieve Context] ──→ [Generate SQL]   │
│                          │                       │           │
│                    Schema + Metrics         LLM + Few-shot   │
│                    từ Vector DB             examples          │
│                          │                       │           │
│                          └───────→ [Validate] ───┘           │
│                                       │                      │
│                                  [Execute SQL]               │
│                                       │                      │
│                               [Generate Insight]             │
│                                       │                      │
│                                  ← Response                  │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

### 1.3 Tại sao chọn approach này?

**So sánh 4 approach phổ biến:**

| Approach | Mô tả | Accuracy | Phù hợp? | Lý do |
|----------|--------|----------|-----------|-------|
| **① Fine-tuned LLM** | Train LLM riêng trên schema/SQL pairs | 70-80% | Không | Cần dataset lớn (10K+ examples), tốn GPU, khó maintain khi schema thay đổi |
| **② Direct Prompting** | Gửi toàn bộ schema + question vào LLM | 60-75% | Không | 14 bảng × 90 columns = prompt quá dài, tốn token, dễ hallucinate |
| **③ RAG + Single LLM** | Retrieve schema liên quan → LLM sinh SQL | 75-85% | Tạm được | Đơn giản hơn, nhưng thiếu self-correction → accuracy bị giới hạn |
| **④ RAG + Validation Pipeline** | Retrieve → LLM sinh SQL → code validate → execute | **85-92%** | **Có** | Accuracy cao nhất, validation layer bắt lỗi trước khi execute, modular |

**3 lý do chính chọn LLM-in-the-middle Pipeline:**

**① Accuracy là ưu tiên số 1 trong domain Banking**
- Sai 1 số trong báo cáo tài chính → hậu quả nghiêm trọng.
- Deterministic validation (code) kiểm tra SQL trước khi execute, self-correct khi sai.
- Snowflake đạt 91% accuracy nhờ semantic layer + multi-step pipeline.

**② Schema 14 bảng vừa đủ phức tạp để cần RAG, chưa đủ lớn để cần fine-tuning**
- 14 bảng, 90 columns = quá nhiều để nhồi vào 1 prompt (Direct Prompting).
- Nhưng chưa đủ lớn (100+ bảng) để justify chi phí fine-tuning.
- RAG chỉ retrieve 2-4 bảng liên quan → context gọn, accuracy cao.

**③ Modular architecture dễ iterate trong Phase R&D**
- Thay đổi LLM? → Chỉ sửa bước SQL Generation.
- Thêm bảng mới? → Update knowledge layer, không cần retrain.
- Accuracy thấp ở pattern nào? → Thêm few-shot examples cho pattern đó.

---

## 2. CÁC COMPONENT/LAYER BẮT BUỘC

### 2.1 Tổng quan kiến trúc phân tầng

Hệ thống bắt buộc phải có **5 layers**, mỗi layer giải quyết 1 nhóm sub-problems:

```
╔══════════════════════════════════════════════════════════════════╗
║  LAYER 1: PRESENTATION                                          ║
║  Giao tiếp với người dùng                                       ║
║  ┌──────────┐  ┌──────────┐  ┌──────────┐                      ║
║  │ REST API │  │ Chat UI  │  │ CLI/SDK  │                      ║
║  └──────────┘  └──────────┘  └──────────┘                      ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 2: PROCESSING PIPELINE                                    ║
║  Xử lý logic nghiệp vụ chính (P1→P6)                           ║
║  ┌────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌────────┐ ║
║  │ Router │→│ Schema   │→│ SQL       │→│Validator│→│Insight │ ║
║  │ [code] │ │ Linker   │ │ Generator │ │ [code]  │ │[LLM]   │ ║
║  │        │ │ [code]   │ │ [LLM] ◄── │ │         │ │optional│ ║
║  └────────┘ └──────────┘ └───────────┘ └─────────┘ └────────┘ ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 3: KNOWLEDGE                                              ║
║  Cung cấp context cho agents                                    ║
║  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            ║
║  │ Semantic     │ │ Vector       │ │ Example      │            ║
║  │ Layer        │ │ Store        │ │ Store        │            ║
║  └──────────────┘ └──────────────┘ └──────────────┘            ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 4: DATA ACCESS                                            ║
║  Truy cập dữ liệu an toàn                                      ║
║  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐            ║
║  │ Connection   │ │ Query        │ │ Audit        │            ║
║  │ Pool         │ │ Executor     │ │ Logger       │            ║
║  └──────────────┘ └──────────────┘ └──────────────┘            ║
╠══════════════════════════════════════════════════════════════════╣
║  LAYER 5: DATA                                                   ║
║  PostgreSQL 18 + pgvector                                       ║
╚══════════════════════════════════════════════════════════════════╝
```

### 2.2 Chi tiết từng component bắt buộc

#### LAYER 1: PRESENTATION — Giao tiếp người dùng

| Component | Vai trò | Bắt buộc? | Ghi chú |
|-----------|---------|-----------|---------|
| **REST API** | Endpoint chính `/api/query` nhận câu hỏi, trả kết quả | **Bắt buộc** | Là xương sống, mọi client đều gọi qua đây |
| **WebSocket** | Streaming response real-time (token by token) | **Bắt buộc** | UX tốt hơn nhiều so với đợi full response 5-10s |
| **Chat UI** | Giao diện web cho business user | Nên có | Streamlit cho POC, React cho production |
| **CLI/SDK** | Cho developer và tự động hóa | Tùy chọn | Có thể bổ sung sau |

#### LAYER 2: PROCESSING PIPELINE — LLM-in-the-middle

**Nguyên tắc:** Chỉ có **1 bước gọi LLM** (SQL Generator). Tất cả bước còn lại là **deterministic code** — không gọi LLM, không thể hallucinate.

| Component | Loại | Sub-problem | Vai trò | Bắt buộc? |
|-----------|------|-------------|---------|-----------|
| **Router** | `code` | P1: Intent | Phân loại câu hỏi: SQL query / clarification / out-of-scope | **Bắt buộc** |
| **Schema Linker** | `code` | P2: Schema Linking | Vector search + dict lookup → build Context Package | **Bắt buộc** |
| **SQL Generator** | `LLM` | P3: SQL Generation | Nhận Context Package → build prompt → gọi LLM → parse SQL | **Bắt buộc** |
| **Validator** | `code` | P4: Validation | SQL parsing + rule checking → pass/fail | **Bắt buộc** |
| **Query Executor** | `code` | P5: Execution | Thực thi SQL read-only với timeout, row limit | **Bắt buộc** |
| **Insight Analyzer** | `LLM` | P6: Presentation | Sinh narrative giải thích kết quả | Tùy chọn (Phase 2+) |
| **Self-Correction Loop** | `code` | P3+P4 | Khi validate/execute fail → feedback cho Generator retry (max 3) | **Bắt buộc** |

**Luồng xử lý chính:**

```
User Question
     │
     ▼
[Router] ─── code ─── Chitchat/Out-of-scope ──→ Từ chối lịch sự
     │
     │ SQL Query
     ▼
[Schema Linker] ─── code ─── Retrieve tables + metrics + examples
     │
     │ Context Package (structured JSON)
     ▼
[SQL Generator] ─── LLM ◄── Bước DUY NHẤT gọi LLM
     │
     │ Generated SQL (string)
     ▼
[Validator] ─── code ─── FAIL? ──→ Error feedback ──→ [SQL Generator] (retry, max 3)
     │
     │ PASS
     ▼
[Executor] ─── code ─── ERROR? ──→ Runtime error ──→ [SQL Generator] (retry)
     │
     │ Result rows
     ▼
[Insight Analyzer] ─── LLM (optional) ─── Format + Narrative
     │
     ▼
Response (SQL + Data + Insight)
```

##### Chi tiết xử lý từng bước KHÔNG dùng LLM:

**ROUTER — `code` — Phân loại intent**

```python
# Logic xử lý: Rule-based classifier hoặc lightweight ML model
# KHÔNG gọi LLM — chỉ pattern matching + keyword detection

def route(question: str) -> Intent:
    # Bước 1: Keyword detection
    sql_keywords = ["bao nhiêu", "top", "tổng", "so sánh", "danh sách",
                     "how many", "total", "list", "compare", "which"]
    chitchat_keywords = ["xin chào", "hello", "cảm ơn", "thanks"]

    # Bước 2: Regex pattern matching
    if matches_any(question, chitchat_keywords):
        return Intent.CHITCHAT

    if matches_any(question, sql_keywords):
        return Intent.SQL_QUERY

    # Bước 3: Fallback — nếu không rõ, hỏi lại user
    return Intent.CLARIFICATION

# Tại sao không cần LLM?
# - Chỉ có 3-4 categories (SQL / Clarification / Chitchat / Out-of-scope)
# - Keyword matching + regex đủ cho 90%+ cases
# - Nếu cần chính xác hơn: dùng lightweight classifier (TF-IDF + SVM)
#   hoặc sentence-transformer + cosine similarity — vẫn KHÔNG cần LLM
```

**SCHEMA LINKER — `code` — Tìm schema liên quan**

```python
# Logic xử lý: Vector search + Dictionary lookup + List filtering
# KHÔNG gọi LLM — hoàn toàn deterministic

def link_schema(question: str) -> ContextPackage:
    # Bước 1: Vector search — tìm domain cluster liên quan
    #   Embed câu hỏi → cosine similarity với cluster embeddings
    #   Input:  "Top 10 merchant doanh thu cao nhất quý trước?"
    #   Output: cluster "transaction_analytics" (score: 0.87)
    embedding = embed_model.encode(question)
    clusters = vector_store.query(embedding, top_k=2)

    # Bước 2: Dict lookup — extract tables + JOIN paths từ cluster
    #   Input:  cluster "transaction_analytics"
    #   Output: tables=[sales, merchants, terminals, products, cards]
    #           joins=["sales.merchant_id = merchants.id", ...]
    tables = DOMAIN_CLUSTERS[clusters[0]]["tables"]
    join_paths = DOMAIN_CLUSTERS[clusters[0]]["join_paths"]

    # Bước 3: Dict lookup — resolve metrics từ semantic layer
    #   Input:  question chứa "doanh thu"
    #   Output: "SUM(sales.total_amount) WHERE status='completed'"
    metrics = {}
    for term, definition in SEMANTIC_LAYER["metrics"].items():
        if any(alias in question.lower() for alias in definition["aliases"]):
            metrics[term] = definition["sql"]

    # Bước 4: Dict lookup — resolve time dimensions
    #   Input:  question chứa "quý trước"
    #   Output: "sale_time >= DATE_TRUNC('quarter', ...) AND ..."
    dimensions = resolve_time_expressions(question)

    # Bước 5: Vector search — tìm few-shot examples tương tự
    #   Input:  question embedding
    #   Output: 2-3 similar Q&A pairs từ golden queries
    examples = example_store.query(embedding, top_k=3)

    # Bước 6: List filter — lấy column enums cho tables liên quan
    enums = {col: vals for col, vals in COLUMN_ENUMS.items()
             if col.split(".")[0] in tables}

    # Bước 7: List filter — sensitive columns
    sensitive = [col for col in SENSITIVE_COLUMNS
                 if col.split(".")[0] in tables]

    return ContextPackage(
        tables=tables,           # schema của các bảng liên quan
        join_paths=join_paths,   # JOIN conditions
        metrics=metrics,         # đã resolve sẵn
        dimensions=dimensions,   # đã resolve sẵn
        examples=examples,       # few-shot Q&A
        enums=enums,             # valid values
        sensitive=sensitive      # cột cấm
    )

# Tại sao không cần LLM?
# - Vector search = cosine similarity (toán học)
# - Metric resolution = dictionary lookup (key → value)
# - JOIN paths = pre-defined trong domain cluster config
# - Tất cả đều deterministic, cho cùng input → cùng output
```

**VALIDATOR — `code` — Kiểm tra SQL**

```python
# Logic xử lý: SQL parsing + Rule-based checking
# KHÔNG gọi LLM — dùng sqlparse library + string matching

def validate(sql: str, context: ContextPackage) -> ValidationResult:
    # Bước 1: Parse SQL syntax
    #   Dùng sqlparse.parse() để check syntax hợp lệ
    try:
        parsed = sqlparse.parse(sql)[0]
    except Exception:
        return ValidationResult(passed=False, error="SQL syntax invalid")

    # Bước 2: Check DML — chỉ cho phép SELECT
    #   Block: INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE
    stmt_type = parsed.get_type()
    if stmt_type != "SELECT":
        return ValidationResult(passed=False,
            error=f"Only SELECT allowed, got {stmt_type}")

    # Bước 3: Check table/column tồn tại
    #   Extract table names từ SQL → so với context.tables
    tables_in_sql = extract_tables(parsed)
    valid_tables = {t["name"] for t in context.tables}
    unknown = tables_in_sql - valid_tables
    if unknown:
        return ValidationResult(passed=False,
            error=f"Unknown tables: {unknown}")

    # Bước 4: Check sensitive columns
    #   Scan SQL string cho các column bị cấm
    columns_in_sql = extract_columns(parsed)
    for col in columns_in_sql:
        if col in context.sensitive:
            return ValidationResult(passed=False,
                error=f"Sensitive column blocked: {col}")

    # Bước 5: Check LIMIT
    #   Nếu không có LIMIT → tự thêm LIMIT 1000
    if "LIMIT" not in sql.upper():
        sql = sql.rstrip(";") + " LIMIT 1000;"

    # Bước 6: EXPLAIN cost estimation (optional)
    #   Chạy EXPLAIN trên DB để estimate cost
    cost = db.execute(f"EXPLAIN (FORMAT JSON) {sql}")
    if cost > COST_THRESHOLD:
        return ValidationResult(passed=False,
            error=f"Query cost too high: {cost}")

    return ValidationResult(passed=True, validated_sql=sql)

# Tại sao không cần LLM?
# - SQL parsing: sqlparse library
# - DML check: string matching trên statement type
# - Table/column check: set intersection
# - Sensitive check: list matching
# - EXPLAIN: PostgreSQL built-in
```

**EXECUTOR — `code` — Thực thi SQL**

```python
# Logic xử lý: Database query execution
# KHÔNG gọi LLM — chỉ psycopg2/asyncpg

def execute(sql: str) -> ExecutionResult:
    # Bước 1: Lấy read-only connection từ pool
    conn = pool.getconn(readonly=True)

    # Bước 2: Set statement timeout
    conn.execute("SET statement_timeout = '30s'")

    # Bước 3: Execute query
    try:
        cursor = conn.execute(sql)
        rows = cursor.fetchall()
        columns = [desc[0] for desc in cursor.description]
    except psycopg2.errors.QueryCanceled:
        return ExecutionResult(success=False, error="Query timeout (30s)")
    except Exception as e:
        return ExecutionResult(success=False, error=str(e))
    finally:
        pool.putconn(conn)

    # Bước 4: Audit log
    audit_logger.log(sql=sql, row_count=len(rows), status="success")

    return ExecutionResult(success=True, columns=columns, rows=rows)
```

#### LAYER 3: KNOWLEDGE — Nền tảng tri thức

Đây là **layer quyết định accuracy**. Snowflake đạt 91% không nhờ LLM giỏi hơn mà nhờ semantic layer tốt hơn.

| Component | Vai trò | Dữ liệu chứa | Bắt buộc? |
|-----------|---------|---------------|-----------|
| **Semantic Layer** | Map business terms → SQL definitions | `"doanh thu" → SUM(sales.total_amount) WHERE status='completed'`, metric definitions, dimension mappings, sensitive columns list | **Bắt buộc** |
| **Vector Store** | Semantic search cho schema + queries | Schema embeddings (chunks theo domain cluster thay vì per-table), query embeddings | **Bắt buộc** |
| **Example Store** | Few-shot learning | 40+ golden queries (hiện có), user corrections (feedback loop), SQL pattern templates | **Bắt buộc** |

**Semantic Layer — ví dụ cấu trúc:**

```
Metrics:    "doanh thu"    → SUM(sales.total_amount) WHERE status='completed'
            "refund rate"  → COUNT(refunds.id) / COUNT(sales.id)
            "khách mới"    → COUNT(*) FROM customers WHERE created_at IN period

Dimensions: "tháng trước"  → DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
            "quý trước"    → DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '1 quarter')

Sensitive:  cards.cvv, cards.card_number, customers.dob, customers.email
```

**Vector Store — cluster-based chunking thay vì flat chunking:**

```
Thay vì:    1 bảng = 1 chunk (mất relationship)
Đổi thành:  1 domain cluster = 1 chunk (giữ JOIN paths)

Ví dụ cluster "transaction_analytics":
  Tables:     sales, merchants, terminals, products, cards
  JOIN paths: sales.merchant_id = merchants.id
              sales.terminal_id = terminals.id
              sales.product_id = products.id
              sales.card_id = cards.id
  Use cases:  revenue analysis, product performance, merchant analytics
```

#### LAYER 4: DATA ACCESS — An toàn dữ liệu

| Component | Vai trò | Bắt buộc? |
|-----------|---------|-----------|
| **Connection Pool** | Read-only connections, pooled (min=2, max=10), isolated transaction | **Bắt buộc** |
| **Query Executor** | `statement_timeout=30s`, auto `LIMIT 1000`, retry logic | **Bắt buộc** |
| **Audit Logger** | Log: who asked, what SQL, when, what result | **Bắt buộc** (compliance banking) |

**Query Safety Rules:**

```
ALLOWED:   SELECT, WITH...SELECT, EXPLAIN SELECT
BLOCKED:   INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE, COPY, DO $$
GUARDED:   SELECT without LIMIT (auto-add), cross-join (warn), full-scan on sales (suggest filter)
FILTERED:  Queries accessing cvv, card_number → block + log
```

#### LAYER 5: DATA — Hạ tầng dữ liệu

| Component | Vai trò | Bắt buộc? |
|-----------|---------|-----------|
| **PostgreSQL 18** | Database chính, chứa business data | **Bắt buộc** (đã có) |
| **pgvector extension** | Vector similarity search cho embeddings | **Bắt buộc** (đã có) |
| **Read Replica** | Tách read traffic khỏi primary | Nên có (production) |

---

## 3. ƯỚC LƯỢNG BÀI TOÁN & CAPACITY PLANNING

### 3.1 Hệ thống phải xử lý được những gì?

#### Phân loại query theo độ phức tạp

Dựa trên 40 queries đã phân tích từ `query.json` + `query_samples.sql`:

| Level | Tỷ lệ dự kiến | SQL Features | Ví dụ | Latency mục tiêu |
|-------|---------------|-------------|-------|-------------------|
| **L1: Simple** | ~40% queries | SELECT, WHERE, GROUP BY, aggregate | "Phân bố KYC status?" | ≤ 3s |
| **L2: Join** | ~35% queries | 1-2 JOINs, multi-table | "Top 10 sản phẩm doanh thu cao nhất?" | ≤ 5s |
| **L3: Advanced** | ~20% queries | CTE, Window functions, HAVING, subquery | "Running cumulative revenue theo tháng?" | ≤ 8s |
| **L4: Complex** | ~5% queries | Self-join, INTERSECT, correlated subquery | "Phát hiện self-transfer?" | ≤ 12s |

#### Yêu cầu functional phải đáp ứng

| # | Capability | Mô tả | Priority |
|---|-----------|-------|----------|
| F1 | Bilingual input | Hiểu câu hỏi tiếng Việt và tiếng Anh | **P0** |
| F2 | Schema linking | Tìm đúng bảng/cột trong 14 tables, 90 columns | **P0** |
| F3 | SQL generation | Sinh PostgreSQL-valid SQL cho L1→L4 | **P0** |
| F4 | Query safety | Block DML, filter sensitive columns, enforce timeout | **P0** |
| F5 | Self-correction | Tự sửa SQL khi validate/execute fail (max 3 retry) | **P0** |
| F6 | Metric resolution | Map "doanh thu" → đúng SQL expression | **P1** |
| F7 | Result insight | Sinh narrative giải thích kết quả | **P1** |
| F8 | Clarification | Hỏi lại khi câu hỏi mơ hồ | **P1** |
| F9 | Conversation context | Hiểu "còn tháng này thì sao?" (follow-up) | **P2** |
| F10 | Query caching | Cache kết quả cho queries lặp lại | **P2** |

### 3.2 Ước lượng lượng người dùng

Đây là **internal enterprise tool**, không phải SaaS public. Ước lượng dựa trên thông tin strategic brief:

| Metric | Phase 1 (POC) | Phase 2 (MVP) | Phase 3 (Production) |
|--------|--------------|---------------|---------------------|
| **Concurrent users** | 3-5 (dev team) | 10-20 (pilot group) | 50-200 (toàn tổ chức) |
| **Queries/ngày** | 50-100 | 200-500 | 1,000-5,000 |
| **Queries/giờ peak** | 10-20 | 50-100 | 200-500 |
| **Avg latency target** | ≤ 10s | ≤ 8s | ≤ 5s |
| **Accuracy target** | ≥ 70% | ≥ 85% | ≥ 90% |

**Nhận xét:** Với ~200-500 queries/giờ peak ở production, đây là workload **thấp đến trung bình**. Bottleneck không nằm ở database I/O hay network, mà nằm ở **LLM API latency** (2-5s/request).

### 3.3 Streaming vs Batch: Phân tích và khuyến nghị

#### Đặc thù bài toán Text-to-SQL

```
Timeline 1 request:

  User gửi câu hỏi
       │
       ▼
  [Schema Linking]      ~0.3-0.5s   (vector search + metric resolve)
       │
       ▼
  [LLM Generate SQL]   ~2-5s        ← BOTTLENECK chính
       │
       ▼
  [Validate SQL]        ~0.1-0.3s   (syntax + safety check)
       │
       ▼
  [Execute SQL]         ~0.2-2s     (tùy query complexity)
       │
       ▼
  [Generate Insight]    ~1-3s       (LLM sinh narrative)
       │
       ▼
  Total: ~4-11s end-to-end
```

#### So sánh Streaming vs Batch

| Tiêu chí | Streaming | Batch |
|----------|-----------|-------|
| **Mô tả** | Response được stream token-by-token ngay khi LLM sinh ra | Đợi toàn bộ pipeline xong → trả 1 response hoàn chỉnh |
| **UX** | User thấy response "đang gõ" → perceived latency thấp | User đợi 5-10s "loading..." → cảm giác chậm |
| **Phù hợp khi** | Interactive chat, single query, user đang chờ | Batch reporting, scheduled reports, multi-query |
| **Complexity** | WebSocket, SSE, chunked transfer | Đơn giản, REST request-response |
| **Error handling** | Phức tạp hơn (stream giữa chừng bị lỗi) | Đơn giản (success/fail rõ ràng) |

#### Khuyến nghị: **Hybrid — ưu tiên Streaming cho interactive, hỗ trợ Batch cho reporting**

```
┌─────────────────────────────────────────────────────────────┐
│                    KHUYẾN NGHỊ: HYBRID                       │
│                                                              │
│  ┌─────────────────────────┐  ┌────────────────────────┐    │
│  │  STREAMING (Primary)    │  │  BATCH (Secondary)     │    │
│  │                         │  │                        │    │
│  │  • Chat UI interaction  │  │  • Scheduled reports   │    │
│  │  • Single question      │  │  • Multi-question      │    │
│  │  • WebSocket/SSE        │  │    batch (5-20 queries) │    │
│  │  • Real-time insight    │  │  • Export to CSV/Excel  │    │
│  │                         │  │  • REST API queue       │    │
│  │  Ưu tiên: Phase 1      │  │  Ưu tiên: Phase 2-3    │    │
│  └─────────────────────────┘  └────────────────────────┘    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Lý do ưu tiên Streaming:**

1. **Use case chính là interactive chat** — User đặt 1 câu hỏi, chờ trả lời. Streaming giảm perceived latency từ ~8s xuống ~1s (user thấy response bắt đầu hiện).

2. **LLM API đã hỗ trợ streaming native** — Claude API, GPT-4 đều có streaming endpoint. Không cần build thêm infra phức tạp.

3. **Batch có thể build sau** — Phase 1 focus interactive, Phase 2-3 mới cần scheduled reports.

**Streaming nên stream những gì:**

| Giai đoạn | Stream? | Lý do |
|-----------|---------|-------|
| Schema linking result | Không | Quá nhanh (~0.5s), không cần stream |
| SQL generation | **Có** | Token-by-token để user thấy SQL đang được sinh |
| SQL validation result | Không | Binary pass/fail |
| Query execution | Không | Đợi full result set |
| Insight narrative | **Có** | Token-by-token giải thích kết quả |

---

## 4. TOP 3 DESIGN PATTERNS PHÙ HỢP

### Pattern 1: LLM-in-the-middle Pipeline (Đề xuất chính)

```
                    ┌──────────────────────────────────────────────┐
                    │           PIPELINE                            │
                    │                                               │
  User Question ──→ │  [Router]  → [Linker]  → [Generator]        │
                    │   code        code         LLM ◄── duy nhất  │
                    │                              │                │
                    │                         ┌────┴────┐           │
                    │                         ▼         │           │
                    │              [Validator] ──FAIL──→ │           │
                    │                code       (retry)  │           │
                    │                │                              │
                    │             PASS                              │
                    │                │                              │
                    │           [Executor] → [Insight] ──→ Response │
                    │             code       LLM (opt)              │
                    │                                               │
                    └──────────────────────────────────────────────┘

  Chú thích:  code = deterministic, không gọi LLM
              LLM  = gọi Claude API (chỉ có 1-2 chỗ)
```

**Mô tả:** Pipeline tuần tự với **1 LLM call ở giữa** (SQL Generator), được bao bọc bởi retrieval code (trước) và validation code (sau). Router, Linker, Validator, Executor đều là deterministic code — không gọi LLM, không thể hallucinate.

| Ưu điểm | Nhược điểm |
|----------|------------|
| Chỉ 1 LLM call → hallucination bị kiểm soát bởi code trước và sau | Latency cao hơn single-call do nhiều bước (~5-8s) |
| Separation of concerns rõ ràng — mỗi bước 1 nhiệm vụ | Nhiều components → phức tạp hơn để maintain |
| Validator (code) bắt lỗi SQL trước khi execute → an toàn | Cần orchestration logic (LangGraph hoặc custom) |
| Dễ debug — biết lỗi ở bước nào (retrieval? LLM? validation?) | Overhead cho queries đơn giản (L1) |
| LLM cost thấp — thực tế chỉ 1 API call/query (không phải 5-6) | Retrieval miss vẫn có thể xảy ra |
| **Accuracy: 85-92%** | **Avg latency: 5-8s** |

**So sánh với phương pháp khác:**

| vs. | LLM-in-the-middle tốt hơn ở | LLM-in-the-middle kém hơn ở |
|-----|-------------------------------|-------------------------------|
| Single LLM call | Accuracy (+15-20%), safety (validator code) | Latency, simplicity |
| True Multi-Agent (nhiều LLM) | Cost thấp hơn (1 LLM call vs 5-6), ít hallucination | Flexibility (true multi-agent linh hoạt hơn) |
| Fine-tuned model | Flexibility, no GPU needed, easy to update | Latency (fine-tuned model nhanh hơn) |

---

### Pattern 2: RAG-Enhanced Single Agent (Đơn giản hóa)

```
  User Question ──→ [RAG Retrieval] ──→ [Single LLM Agent] ──→ Response
                         │                      │
                    Schema + Examples       Generate SQL +
                    + Metrics              Execute + Explain
                                           (all in one prompt)
```

**Mô tả:** Một LLM agent duy nhất xử lý tất cả: nhận context từ RAG, sinh SQL, tự validate, tự execute (qua tool use), tự giải thích kết quả. Tất cả trong 1 conversation turn.

| Ưu điểm | Nhược điểm |
|----------|------------|
| Đơn giản nhất — ít code, ít component | Accuracy thấp hơn (~75-85%) vì không có chuyên biệt hóa |
| Latency thấp — 1 LLM call (3-6s) | Khó debug — lỗi ở đâu trong pipeline? |
| Chi phí LLM thấp — 1 API call/query | Prompt dài (schema + rules + examples + output format) |
| Dễ prototype nhanh (Phase 1 POC) | Safety checks yếu — LLM tự validate chính nó |
| Ít moving parts → ít failure points | Khó mở rộng khi thêm tables hoặc features |
| **Accuracy: 75-85%** | **Avg latency: 3-6s** |

**So sánh với phương pháp khác:**

| vs. | Single Agent tốt hơn ở | Single Agent kém hơn ở |
|-----|------------------------|------------------------|
| LLM-in-the-middle Pipeline | Speed, simplicity, cost | Accuracy, safety, debuggability |
| Direct Prompting (no RAG) | Accuracy (+10-15%), token efficiency | Slightly more complex (RAG setup) |
| Fine-tuned model | Flexibility, no training needed | Speed, offline capability |

---

### Pattern 3: Adaptive Router + Tiered Agents (Tối ưu)

```
  User Question ──→ [Adaptive Router]
                         │
              ┌──────────┼──────────┐
              │          │          │
         L1: Simple  L2-L3: Med  L4: Complex
              │          │          │
              ▼          ▼          ▼
         [Fast Path] [Standard]  [Deep Path]
         Single LLM  Full pipeline Full pipeline
         No validate + validation  + extended
         ~2-3s       ~5-8s         reasoning
                                   ~10-15s
```

**Mô tả:** Router (code) phân loại query complexity, sau đó dispatch vào pipeline phù hợp. Query đơn giản đi "fast path" (1 LLM call, skip validation), query phức tạp đi "deep path" (full pipeline + extended reasoning).

| Ưu điểm | Nhược điểm |
|----------|------------|
| Tối ưu latency: query đơn giản nhanh, phức tạp mới chậm | Router phải classify đúng — sai = sai cả pipeline |
| Tối ưu cost: không chạy full pipeline cho L1 queries | Phức tạp nhất trong 3 patterns |
| Best of both worlds — speed + accuracy | 3 paths = 3x testing/maintenance effort |
| Scalable — thêm tier mới khi cần | Router accuracy là single point of failure |
| Phù hợp cho production long-term | Cần nhiều data để train/tune Router |
| **Accuracy: 85-92%** | **Avg latency: 2-8s (adaptive)** |

**So sánh với phương pháp khác:**

| vs. | Adaptive Router tốt hơn ở | Adaptive Router kém hơn ở |
|-----|---------------------------|---------------------------|
| Fixed Pipeline | Speed cho simple queries, cost efficiency | Complexity, router accuracy risk |
| Single Agent | Accuracy cho complex queries | Simplicity |
| Fine-tuned + RAG | Flexibility, no GPU | Cold-start latency, dependency on LLM API |

---

### Tổng hợp so sánh 3 Patterns

| Tiêu chí | Pattern 1: LLM-in-the-middle | Pattern 2: RAG Single Agent | Pattern 3: Adaptive Router |
|----------|------------------------------|----------------------------|---------------------------|
| **Accuracy** | ⭐⭐⭐⭐⭐ 85-92% | ⭐⭐⭐ 75-85% | ⭐⭐⭐⭐⭐ 85-92% |
| **Latency** | ⭐⭐⭐⭐ 5-8s | ⭐⭐⭐⭐⭐ 3-6s | ⭐⭐⭐⭐ 2-8s adaptive |
| **Complexity** | ⭐⭐⭐ Trung bình | ⭐⭐⭐⭐⭐ Thấp | ⭐⭐ Cao |
| **Safety** | ⭐⭐⭐⭐⭐ Validator code riêng | ⭐⭐ LLM tự validate | ⭐⭐⭐⭐ Validate cho L2+ |
| **Cost (LLM)** | ⭐⭐⭐⭐ Thấp (thực tế 1 call) | ⭐⭐⭐⭐⭐ Thấp (1 call) | ⭐⭐⭐⭐ Tối ưu theo tier |
| **Maintainability** | ⭐⭐⭐⭐ Modular | ⭐⭐⭐⭐ Đơn giản | ⭐⭐ 3 paths |
| **Debuggability** | ⭐⭐⭐⭐⭐ Rõ từng step | ⭐⭐ Black-box | ⭐⭐⭐⭐ Rõ sau routing |
| **Hallucination risk** | ⭐⭐⭐⭐⭐ Thấp (code bọc LLM) | ⭐⭐⭐ Trung bình | ⭐⭐⭐⭐ Thấp cho L2+ |
| **Phù hợp Banking** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |

### Khuyến nghị lộ trình

```
Phase 1 (R&D):     Bắt đầu với Pattern 2 (Single Agent) → validate feasibility nhanh
                    ↓
Phase 2 (POC):     Tiến hóa sang Pattern 1 (LLM-in-the-middle) → đạt accuracy target 85%+
                    ↓
Phase 3 (Prod):    Tối ưu thành Pattern 3 (Adaptive Router) → tối ưu latency + cost
```

**Lý do lộ trình này hợp lý:**
- Phase 1: Pattern 2 cho phép prototype trong 2-3 tuần, validate RAG approach nhanh.
- Phase 2: Refactor sang Pattern 1 khi cần accuracy cao hơn. Code Pattern 2 trở thành SQL Generator agent.
- Phase 3: Thêm Adaptive Router lên trên Pattern 1 để tối ưu. Không cần rewrite, chỉ thêm routing layer.

---

## 5. ĐỀ XUẤT TECH STACK

### 5.1 Tech Stack cho từng Pattern

#### Pattern 2 — RAG Single Agent (Phase 1)

| Layer | Component | Lựa chọn | Lý do chọn |
|-------|-----------|----------|------------|
| **LLM** | Primary | **Claude claude-sonnet-4-6 (Anthropic)** | Tool use native tốt nhất thị trường, accuracy cao trên SQL generation, hỗ trợ tiếng Việt tốt, cost hợp lý ($3/$15 per 1M tokens) |
| **Embedding** | Model | **bge-large-en-v1.5** (hiện tại) → **bge-m3** (upgrade) | bge-m3 hỗ trợ multilingual (tiếng Việt), dense + sparse retrieval, outperform bge-large trên non-English |
| **Vector DB** | Dev | **ChromaDB** (hiện tại) | Đã setup, đủ cho POC với <100 documents |
| **Framework** | Agent | **Claude Tool Use (native)** | Không cần framework phức tạp. Claude hỗ trợ tool/function calling trực tiếp. Giảm dependency |
| **API** | Web | **FastAPI** | Async native (phù hợp streaming), auto OpenAPI docs, WebSocket support, ecosystem Python lớn |
| **Database** | Primary | **PostgreSQL 18 + pgvector** (hiện tại) | Đã setup. pgvector cho vector search, consolidate 1 DB |

**Tại sao Claude Sonnet mà không phải GPT-4o hay DeepSeek?**

| Model | SQL Accuracy* | Tool Use | Vietnamese | Cost (1M tokens) | Nhận xét |
|-------|-------------|----------|-----------|------------------|----------|
| **Claude claude-sonnet-4-6** | ~87% | ⭐⭐⭐⭐⭐ Native | ⭐⭐⭐⭐ Tốt | $3 / $15 | **Best balance** accuracy + tool use + cost |
| GPT-4o | ~85% | ⭐⭐⭐⭐ Tốt | ⭐⭐⭐⭐ Tốt | $2.5 / $10 | Rẻ hơn nhưng tool use kém structured hơn |
| DeepSeek V3 | ~80% | ⭐⭐⭐ Khá | ⭐⭐⭐ Trung bình | $0.27 / $1.1 | Rất rẻ nhưng accuracy và tool use chưa bằng |
| Qwen 2.5 72B | ~78% | ⭐⭐⭐ Khá | ⭐⭐⭐⭐⭐ Xuất sắc | Self-hosted | Cần GPU, Vietnamese tốt nhất nhưng cần infra |

*Ước lượng dựa trên benchmark Spider/Bird và internal testing patterns tương tự.*

---

#### Pattern 1 — LLM-in-the-middle Pipeline (Phase 2)

Kế thừa toàn bộ stack Phase 1, bổ sung:

| Layer | Component | Lựa chọn | Lý do chọn |
|-------|-----------|----------|------------|
| **LLM** | Complex queries | **Claude claude-opus-4-6** | Cho L3-L4 queries cần reasoning sâu (CTE, window functions, correlated subquery). Fallback khi Sonnet fail sau 3 retries |
| **Framework** | Orchestration | **LangGraph** | Graph-based agent routing, built-in state management, conditional edges (retry loop), streaming support. Mature hơn custom code |
| **Cache** | Query | **Redis** | Cache kết quả cho queries lặp lại, session state cho conversation context. Standard, fast, proven |
| **Vector DB** | Prod | **PostgreSQL pgvector** (consolidate) | Giảm infra complexity. pgvector đủ performance cho <10K embeddings. Không cần maintain ChromaDB riêng |
| **Monitoring** | Observability | **Langfuse** (LLM-specific) | Trace từng LLM call, prompt versioning, cost tracking, accuracy monitoring. Purpose-built cho LLM apps |

**Tại sao LangGraph mà không phải LangChain, CrewAI, hay Custom code?**

| Framework | Phù hợp | Không phù hợp | Verdict |
|-----------|---------|---------------|---------|
| **LangGraph** | Graph-based workflows, conditional routing, state management, streaming | Learning curve, tied to LangChain ecosystem | **Chọn** — đủ linh hoạt cho pipeline phức tạp, native streaming |
| LangChain | RAG pipelines, simple chains | Over-abstraction, performance overhead, breaking changes thường xuyên | Quá nhiều abstraction cho bài toán agent |
| CrewAI | Multi-agent collaboration, role-based agents | Less control over execution flow, opinionated design | Quá prescriptive, ít control |
| Custom Python | Full control, no dependency | Phải tự build state management, retry logic, streaming | Tốn effort, dễ có bug ở edge cases |
| AutoGen | Research-oriented multi-agent | Still maturing, complex setup, heavy framework | Quá nặng cho production |

---

#### Pattern 3 — Adaptive Router (Phase 3)

Kế thừa toàn bộ stack Phase 2, bổ sung:

| Layer | Component | Lựa chọn | Lý do chọn |
|-------|-----------|----------|------------|
| **Router** | Classification | **Claude Haiku** (fast) | Classify query complexity (L1/L2/L3/L4) với latency ~0.3s, cost cực thấp ($0.25/$1.25 per 1M tokens). Chỉ cần classify, không cần reasoning |
| **UI** | Frontend | **React + TailwindCSS** | Production-grade UX, component reusability, SSE/WebSocket streaming, mobile-responsive |
| **API Gateway** | Rate limiting | **Nginx** | Reverse proxy, rate limiting, SSL termination. Standard, proven |
| **Monitoring** | Full stack | **Prometheus + Grafana** (infra) + **Langfuse** (LLM) | Prometheus/Grafana cho system metrics, Langfuse cho LLM-specific metrics |

---

### 5.2 Tổng hợp Tech Stack theo Phase

```
┌───────────────────────────────────────────────────────────────────┐
│                    TECH STACK EVOLUTION                            │
│                                                                   │
│  PHASE 1 (R&D)              PHASE 2 (POC)         PHASE 3 (Prod) │
│  ─────────────              ─────────────          ────────────── │
│                                                                   │
│  Claude Sonnet ──────────→  + Claude Opus  ──────→ + Claude Haiku │
│  (primary)                  (complex queries)      (router)       │
│                                                                   │
│  Claude Tool Use ────────→  LangGraph      ──────→ LangGraph      │
│  (native, simple)           (orchestration)        (multi-tier)   │
│                                                                   │
│  FastAPI ────────────────→  FastAPI         ──────→ FastAPI+Nginx  │
│                                                                   │
│  ChromaDB ───────────────→  pgvector       ──────→ pgvector       │
│  (dev convenience)          (consolidate)                         │
│                                                                   │
│  bge-large-en ───────────→  bge-m3         ──────→ bge-m3         │
│                             (multilingual)                        │
│                                                                   │
│  Streamlit ──────────────→  Streamlit       ──────→ React          │
│  (quick POC)                (enhanced)             (production)   │
│                                                                   │
│  (none) ─────────────────→  Redis          ──────→ Redis          │
│                             (cache)                               │
│                                                                   │
│  (none) ─────────────────→  Langfuse       ──────→ Langfuse +     │
│                             (LLM monitoring)       Prometheus +   │
│                                                    Grafana        │
│                                                                   │
│  PostgreSQL 18 + pgvector  (xuyên suốt cả 3 phases)              │
│  Python 3.11+              (xuyên suốt cả 3 phases)              │
│                                                                   │
└───────────────────────────────────────────────────────────────────┘
```

### 5.3 Tóm tắt lý do lựa chọn tech stack

| Quyết định | Lý do chính | Trade-off chấp nhận |
|-----------|-------------|---------------------|
| **Claude API > self-hosted LLM** | Accuracy cao, tool use tốt, không cần GPU | Phụ thuộc external API, có latency mạng |
| **LangGraph > custom code** | Pipeline state management, conditional routing (retry loop), streaming built-in | Learning curve, LangChain ecosystem dependency |
| **pgvector > dedicated vector DB** | Giảm infra (1 DB cho tất cả), đủ cho <10K embeddings | Performance kém hơn Pinecone/Weaviate ở scale lớn |
| **FastAPI > Django/Flask** | Async native, WebSocket, auto docs | Ecosystem nhỏ hơn Django |
| **bge-m3 > bge-large-en** | Multilingual (Vietnamese!), dense+sparse | Model lớn hơn, embedding chậm hơn ~20% |
| **Redis > in-memory cache** | Persistent, shared across instances, proven | Thêm 1 service phải maintain |
| **Langfuse > custom logging** | Purpose-built cho LLM: trace, cost, prompt versioning | SaaS dependency (có self-hosted option) |
| **Streamlit → React** | Streamlit nhanh cho POC, React cho UX production | Phải rewrite frontend ở Phase 3 |

---

## PHỤ LỤC: DECISION MATRIX

### Scoring tổng thể (weighted)

Trọng số dựa trên yêu cầu domain Banking/POS:

| Tiêu chí | Trọng số | Pattern 1 | Pattern 2 | Pattern 3 |
|----------|---------|-----------|-----------|-----------|
| Accuracy | 30% | 9/10 | 7/10 | 9/10 |
| Safety/Compliance | 25% | 10/10 | 5/10 | 8/10 |
| Latency/UX | 15% | 6/10 | 9/10 | 8/10 |
| Development Cost | 15% | 6/10 | 9/10 | 5/10 |
| Maintainability | 10% | 8/10 | 8/10 | 6/10 |
| Scalability | 5% | 7/10 | 5/10 | 9/10 |
| **Weighted Score** | **100%** | **8.15** | **7.15** | **7.70** |

**Kết luận:** Pattern 1 (LLM-in-the-middle Pipeline) đạt điểm cao nhất nhờ accuracy và safety — hai yếu tố quan trọng nhất trong domain Banking. Tuy nhiên, lộ trình **Pattern 2 → 1 → 3** là con đường thực tế nhất vì cho phép validate nhanh rồi tiến hóa dần.

---

## 6. PHÂN TÍCH SCALE-UP

### 6.1 Quy mô hiện tại vs. Scale-up

Kiến trúc hiện tại được thiết kế cho **small schema**. Khi scale lên, có 3 ngưỡng gãy quan trọng:

| Quy mô | Bảng | Columns | Rows (bảng lớn nhất) | Vấn đề xuất hiện |
|--------|------|---------|---------------------|-------------------|
| **Small** (hiện tại) | 14 | 90 | 200K | Không — approach hiện tại đủ |
| **Medium** | 50-100 | 300-500 | 1-10M | Retrieval accuracy giảm, domain clusters chồng chéo, context window LLM bắt đầu bị đầy |
| **Large** | 200+ | 1000+ | 100M+ | Không thể nhồi schema vào 1 prompt, embedding space quá rộng, ambiguity tăng mạnh |

### 6.2 Thay đổi cần thiết theo từng ngưỡng

#### Ngưỡng Medium (50-100 bảng)

| Component | Hiện tại (Small) | Cần thay đổi | Lý do |
|-----------|-----------------|---------------|-------|
| **Vector Store** | pgvector (đủ <10K embeddings) | Pinecone / Weaviate | ANN index tốt hơn, metadata filtering phức tạp hơn, horizontal scaling |
| **Retrieval** | 1-step: query → top-K chunks | **2-step hierarchical**: query → cluster → tables trong cluster | 1-step retrieve trên 100 bảng accuracy giảm, cần thu hẹp search space trước |
| **Domain Clusters** | 7 clusters, quản lý thủ công | Semi-auto clustering + manual review | 100 bảng → 20-30 clusters, maintain thủ công không khả thi |
| **LLM Context** | Đưa 2-4 bảng (fit prompt) | Đưa 3-5 bảng + schema summary cho bảng liên quan | Token budget tăng, cần selective column inclusion |
| **Embedding Model** | bge-m3 (multilingual) | + domain fine-tuned adapter | Generic embedding kém khi schema terms quá chuyên biệt |

```
Hierarchical Retrieval (2-step):

  User Question
       │
       ▼
  Step 1: "Cluster nào liên quan?"
       │   Query embedding vs. cluster description embeddings
       │   → Top 2-3 clusters
       ▼
  Step 2: "Bảng nào trong cluster đó?"
       │   Query embedding vs. table embeddings (trong cluster đã chọn)
       │   → Top 3-5 tables + JOIN paths
       ▼
  Context Package → SQL Generator
```

#### Ngưỡng Large (200+ bảng)

| Component | Cần thay đổi | Lý do |
|-----------|---------------|-------|
| **Schema Catalog** | Schema catalog service riêng biệt (giống data catalog) | 200+ bảng cần indexing, versioning, lineage tracking |
| **Retrieval** | **Multi-hop retrieval**: query → domain → sub-domain → tables | 2-step không đủ khi có 50+ clusters |
| **Embedding** | Fine-tuned embedding model trên schema corpus | Generic model không capture được domain-specific semantics ở scale lớn |
| **LLM** | Selective column pruning + schema compression | 200 bảng × 10 columns = 2000 columns, không thể đưa hết vào context |
| **Query Execution** | Table partitioning, materialized views, query plan advisor | Billions of rows cần optimization ở DB level |
| **Caching** | Multi-layer cache: embedding cache + query result cache + LLM response cache | Giảm latency và cost tại mọi layer |

### 6.3 Chiến lược Scale-up khuyến nghị

```
Scale sớm (không cần chờ bottleneck):
  ✓ Connection pooling + read replica       → sẵn sàng từ đầu
  ✓ Modular agent design                    → swap component dễ
  ✓ Schema metadata versioning              → track schema changes

Scale khi cần (khi thấy bottleneck thực tế):
  ⟳ pgvector → dedicated vector DB          → khi retrieval accuracy < 85%
  ⟳ 1-step → hierarchical retrieval         → khi số bảng > 50
  ⟳ Generic → fine-tuned embedding          → khi domain terms quá chuyên biệt
  ⟳ Single DB → partitioned + materialized  → khi query latency > 5s

Không cần scale quá sớm (over-engineering):
  ✗ Kubernetes orchestration                 → Docker Compose đủ cho < 500 users
  ✗ Multi-region deployment                  → Single region đủ cho internal tool
  ✗ Custom-trained LLM                       → API-based LLM đủ cho < 100 bảng
```

**Kết luận:** Với scope Banking/POS hiện tại (14 bảng), kiến trúc hiện tại đủ cho Phase 1-3. Modular design cho phép swap từng component khi scale mà không cần rewrite toàn bộ. Ưu tiên scale **retrieval layer** trước vì đó là bottleneck đầu tiên khi số bảng tăng.

---

## 7. SCHEMA LINKER — CƠ CHẾ PHÁT HIỆN RELATIONSHIP

### 7.1 Nguồn relationship: Auto-detect + User-defined

Schema Linker sử dụng **2 nguồn** để xây dựng relationship map (một Python dict đơn giản, **không phải graph database**):

```
┌─────────────────────────────────────────────────────────────┐
│                  RELATIONSHIP SOURCES                        │
│                                                              │
│  ┌──────────────────────────────┐                           │
│  │  SOURCE 1: AUTO-DETECT      │  ← Primary (tự động)      │
│  │  (từ cấu trúc DB hiện có)    │                           │
│  │                              │                           │
│  │  • schema.json relationships │  13 FK đã define sẵn      │
│  │  • INFORMATION_SCHEMA        │  Validate FK constraints  │
│  │  • Column naming conventions │  xxx_id → FK pattern      │
│  │  • REFERENCES constraints    │  DDL-level FK             │
│  └──────────────┬───────────────┘                           │
│                 │                                            │
│                 ▼ merge                                      │
│          ┌──────────────────┐                               │
│          │ RELATIONSHIP MAP │                               │
│          │ (Python dict)    │ → {"sales.merchant_id":       │
│          │                  │    "merchants.id", ...}       │
│          └──────────────────┘                               │
│                 ▲ enrich                                     │
│                 │                                            │
│  ┌──────────────┴───────────────┐                           │
│  │  SOURCE 2: USER-DEFINED     │  ← Enrichment (thủ công)  │
│  │  (semantic layer config)     │                           │
│  │                              │                           │
│  │  • Business aliases          │  "doanh thu" → tables     │
│  │  • Self-referencing patterns │  transfers: from/to       │
│  │  • Implicit relationships    │  Không có FK nhưng có     │
│  │  • Disambiguation rules      │  logic relationship       │
│  │  • Domain cluster overrides  │                           │
│  └──────────────────────────────┘                           │
│                                                              │
│  LƯU Ý: "Relationship map" = Python dictionary              │
│  KHÔNG phải: Neo4j, Knowledge Graph, hay Graph Database     │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 7.2 Auto-detect — Từ cấu trúc DB

#### Nguồn 1: `schema.json` (đã có sẵn)

```json
// schema.json đã define relationships rõ ràng:

// employees → branches
"relationships": [
  {"from": "branch_id", "to": "branches.id", "type": "many-to-one"}
]

// accounts → customers
"relationships": [
  {"from": "customer_id", "to": "customers.id", "type": "many-to-one"}
]

// sales → merchants, terminals, products, cards
"relationships": [
  {"from": "merchant_id", "to": "merchants.id", "type": "many-to-one"},
  {"from": "terminal_id", "to": "terminals.id", "type": "many-to-one"},
  {"from": "product_id", "to": "products.id", "type": "many-to-one"},
  {"from": "card_id", "to": "cards.id", "type": "many-to-one"}
]
```

**Coverage:** Auto-detect từ `schema.json` bắt được **13/13 FK relationships** trong schema hiện tại.

#### Nguồn 2: PostgreSQL metadata (validation + bổ sung)

```sql
-- Query INFORMATION_SCHEMA để cross-validate FK relationships
SELECT
  tc.table_name       AS source_table,
  kcu.column_name     AS source_column,
  ccu.table_name      AS target_table,
  ccu.column_name     AS target_column
FROM information_schema.table_constraints tc
JOIN information_schema.key_column_usage kcu
  ON tc.constraint_name = kcu.constraint_name
JOIN information_schema.constraint_column_usage ccu
  ON tc.constraint_name = ccu.constraint_name
WHERE tc.constraint_type = 'FOREIGN KEY';
```

**Vai trò:** Cross-validate với `schema.json` — nếu schema.json thiếu FK, DB metadata bổ sung. Nếu schema.json có FK mà DB không có → cảnh báo inconsistency.

### 7.3 User-defined — Cho những gì auto-detect không bắt được

| Loại | Ví dụ | Tại sao auto-detect không bắt |
|------|-------|-------------------------------|
| **Self-referencing semantics** | `transfers.from_account` và `transfers.to_account` đều → `accounts.id` | FK tồn tại, nhưng semantic "from" vs "to" cần human label để LLM hiểu đây là 2 roles khác nhau |
| **Business term → table mapping** | "doanh thu" liên quan đến `sales`, không phải `statements` | Không có trong DB metadata, đây là domain knowledge |
| **Implicit relationships** | "merchant performance" cần JOIN `sales → merchants → terminals` | Mỗi FK riêng lẻ có trong DB, nhưng "performance" là concept business cần human define path |
| **Disambiguation** | `customers.created_at` vs `accounts.opened_at` — cái nào là "ngày onboard"? | Cả hai đều là timestamp, DB không biết cái nào mang nghĩa business |
| **Domain cluster grouping** | Nhóm `sales + merchants + terminals + products` thành "transaction_analytics" | DB metadata không có concept "domain", cần human organize |

### 7.4 Linker Boot Process — 2 giai đoạn

```
BOOT TIME (1 lần khi khởi động, hoặc khi schema thay đổi)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

  Bước 1: Parse schema.json
    → Extract 14 tables, 90 columns, 13 relationships
    → Build relationship map (Python dict: FK column → PK column)

  Bước 2: Query INFORMATION_SCHEMA (optional, validation)
    → Cross-validate FK constraints với schema.json
    → Log warnings nếu inconsistency

  Bước 3: Load semantic layer config
    → Overlay business aliases, domain clusters, sensitive columns
    → Merge user-defined relationships vào dict

  Bước 4: Generate embeddings
    → Cluster-based chunks (per domain cluster)
    → Upsert vào vector store

  Output: Relationship Map (dict) + Embedded Chunks sẵn sàng

RUNTIME (mỗi query)
━━━━━━━━━━━━━━━━━━

  Input:  User question
  Step 1: Vector search → relevant domain cluster(s)
  Step 2: Dict lookup → extract tables + JOIN paths từ cluster
  Step 3: Resolve metrics + dimensions từ semantic layer
  Step 4: Fetch few-shot examples tương tự
  Output: Context Package → SQL Generator
```

---

## 8. PIPELINE COMMUNICATION & HALLUCINATION

### 8.1 Vấn đề đặt ra

> Nếu tách Linker và Generator thành 2 bước riêng, Generator có đủ thông tin về relationships không? Truyền qua nhiều bước có tăng hallucination không?

**Clarification quan trọng:** Pipeline này **KHÔNG phải multi-agent** (nhiều LLM nói chuyện với nhau). Chỉ có **1 LLM call** (SQL Generator). Các bước khác (Router, Linker, Validator, Executor) là **deterministic code** — không gọi LLM, không thể hallucinate. Xem [Section 2.2 - Chi tiết xử lý từng bước](#chi-tiết-xử-lý-từng-bước-không-dùng-llm) cho logic code cụ thể.

### 8.2 Generator nhận được gì từ Linker?

Linker (code) **không chỉ trả về tên bảng**. Output của Linker là **Context Package** — một structured JSON chứa đầy đủ thông tin:

```
Ví dụ: User hỏi "Top 10 merchant có doanh thu cao nhất quý trước?"

┌──── CONTEXT PACKAGE (Linker → Generator) ────┐
│                                               │
│  tables: [                                    │
│    {                                          │
│      name: "merchants",                       │
│      columns: [id, name, mcc, city],          │  ← CHỈ columns liên quan
│      description: "Merchants where..."        │    không phải toàn bộ schema
│    },                                         │
│    {                                          │
│      name: "sales",                           │
│      columns: [id, merchant_id, total_amount, │
│                status, sale_time],             │
│      description: "Records of sales..."       │
│    }                                          │
│  ]                                            │
│                                               │
│  join_paths: [                                │
│    "sales.merchant_id = merchants.id"         │  ← JOIN ĐẦY ĐỦ
│  ]                                            │
│                                               │
│  resolved_metrics: {                          │
│    "doanh thu":                               │  ← ĐÃ RESOLVE sẵn
│      "SUM(sales.total_amount)                 │
│       WHERE sales.status = 'completed'"       │
│  }                                            │
│                                               │
│  resolved_dimensions: {                       │
│    "quý trước":                               │  ← ĐÃ RESOLVE sẵn
│      "sale_time >= DATE_TRUNC('quarter',      │
│       CURRENT_DATE - INTERVAL '1 quarter')    │
│       AND sale_time < DATE_TRUNC('quarter',   │
│       CURRENT_DATE)"                          │
│  }                                            │
│                                               │
│  few_shot_examples: [                         │
│    {                                          │  ← VÍ DỤ TƯƠNG TỰ
│      q: "Top 5 sản phẩm doanh thu cao nhất?" │
│      sql: "SELECT p.name, SUM(...) ..."       │
│    }                                          │
│  ]                                            │
│                                               │
│  sensitive_columns: [                         │
│    "cards.cvv", "cards.card_number"            │  ← DANH SÁCH CẤM
│  ]                                            │
│                                               │
│  column_enums: {                              │
│    "sales.status":                            │  ← GIÁ TRỊ HỢP LỆ
│      ["completed","pending","failed",         │
│       "reversed"]                             │
│  }                                            │
│                                               │
└───────────────────────────────────────────────┘
```

**Generator nhận structured data**, không phải mô tả bằng ngôn ngữ tự nhiên. Nó biết chính xác:
- Bảng nào, column nào → không bịa table/column
- JOIN condition cụ thể → không đoán relationship
- Metric đã resolve → không diễn giải sai "doanh thu"
- Enum values → không bịa status value

### 8.3 Pipeline này có tăng hallucination không?

**Không. Pipeline này thực tế GIẢM hallucination so với single LLM call.**

Lý do: Đây không phải multi-agent (nhiều LLM truyền tin cho nhau). Đây là **1 LLM được bọc bởi code**:

```
[code] → [code] → [LLM] → [code] → [code]
  ↑         ↑        ↑        ↑        ↑
Router   Linker  Generator Validator Executor
                     │
              Chỗ DUY NHẤT có thể hallucinate
```

#### So sánh: LLM-in-the-middle vs Single LLM call

| Yếu tố | Single LLM call (Pattern 2) | LLM-in-the-middle (Pattern 1) |
|---------|----------------------------|-------------------------------|
| **Prompt size** | Dài — toàn bộ 14 bảng × 90 columns + rules + examples | Ngắn — chỉ 2-5 bảng liên quan (Linker đã filter) |
| **Task cho LLM** | LLM phải: tìm bảng + resolve metric + chọn JOIN + sinh SQL + validate | LLM chỉ: sinh SQL (context đã chuẩn bị sẵn bởi code) |
| **Khi LLM bịa column** | Không ai kiểm tra → SQL fail ở runtime | Validator (code) bắt ngay → retry với error message |
| **Khi metric bị hiểu sai** | LLM tự diễn giải "doanh thu" → có thể sai | Code đã resolve sẵn → đúng definition, LLM không cần đoán |
| **Hallucination surface** | **Lớn** — LLM chịu trách nhiệm mọi thứ | **Nhỏ** — LLM chỉ chịu trách nhiệm sinh SQL từ context đã verify |

#### Tại sao các bước code KHÔNG gây hallucination?

```
Router    = keyword matching + regex       → Deterministic
Linker    = vector search + dict lookup    → Deterministic (xem Section 2.2)
Validator = sqlparse + rule checking       → Deterministic (xem Section 2.2)
Executor  = psycopg2.execute()             → Deterministic

→ Không bước nào gọi LLM → Không có cơ hội hallucinate
→ Output giữa các bước là structured data (JSON) → Không mất thông tin khi truyền
```

#### Rủi ro thực tế: Retrieval Miss (không phải hallucination)

```
Rủi ro thực tế KHÔNG phải hallucination mà là RETRIEVAL MISS:

  User hỏi: "Tỷ lệ refund theo merchant"

  ✗ Linker retrieve SAI:
    → Cluster "transaction_analytics" (có sales, merchants — THIẾU refunds!)
    → Generator sinh SQL không có refunds table
    → Kết quả SAI (nhưng SQL valid syntactically)

  ✓ Linker retrieve ĐÚNG:
    → Cluster "refund_analysis" (có refunds, sales, merchants)
    → Generator có đủ context → SQL đúng

  Giải pháp retrieval miss:
    1. Cải thiện embedding quality (bge-m3 thay bge-large-en)
    2. Overlap domain clusters (refunds xuất hiện trong cả 2 clusters)
    3. Multi-cluster retrieval (top-2 clusters thay vì top-1)
    4. User feedback loop (sai → user sửa → update embeddings)
```

### 8.4 Nguyên tắc thiết kế pipeline

Để pipeline giảm thiểu hallucination, tuân thủ 3 nguyên tắc:

| # | Nguyên tắc | Mô tả | Vi phạm → hậu quả |
|---|-----------|-------|---------------------|
| **1** | **Code bọc LLM** | Các bước trước/sau LLM phải là deterministic code, không phải LLM khác | Nhiều LLM nói chuyện với nhau → hallucination lan truyền + khuếch đại |
| **2** | **Structured data giữa các bước** | Output mỗi bước là JSON/typed objects, KHÔNG phải natural language | NL truyền giữa các bước → mất thông tin, drift |
| **3** | **Retrieve trước, Generate sau** | Code chuẩn bị đầy đủ context (tables + JOINs + metrics + enums) TRƯỚC khi gọi LLM | LLM phải vừa retrieve vừa generate → prompt overload → hallucinate |

---

## 9. PHÂN TÍCH MỨC ĐỘ PHỤ THUỘC LLM THEO PATTERN

### 9.1 Tổng quan

Một câu hỏi quan trọng khi lựa chọn design pattern: **Chất lượng mô hình LLM chiếm bao nhiêu phần trăm trong thành công tổng thể?** Phần này phân tích vai trò LLM so với các thành phần khác (code, data, engineering) trên cả 3 patterns, từ đó giúp quyết định nên đầu tư effort vào đâu.

### 9.2 Pattern 2: RAG Single Agent — LLM chiếm ~50%

```
User Question → [RAG Retrieval] → [Single LLM Agent] → Response
                    code              LLM làm TẤT CẢ
```

LLM phải tự làm **5 việc trong 1 prompt**: tìm bảng đúng từ context RAG trả về, resolve metric, chọn JOIN path, sinh SQL, tự validate.

| Thành phần | % đóng góp | Ghi chú |
|---|---|---|
| **RAG Retrieval quality** | ~20-25% | Chỉ đưa context thô, LLM phải tự lọc |
| **LLM model quality** | **~45-55%** | Gánh gần như toàn bộ logic |
| **Few-shot examples** | ~10-15% | Quan trọng hơn vì không có validator |
| **Prompt engineering** | ~10-15% | Rules, output format, constraints trong prompt |
| **Validator/Safety** | ~0% | Không có — LLM tự validate chính nó |

**Tại sao LLM chiếm >50%?**
- LLM vừa phải **retrieve** (chọn bảng đúng từ context dài), vừa **generate** (sinh SQL), vừa **validate** (tự check).
- Không có code validator → lỗi hallucination đi thẳng ra output.
- Đổi từ Sonnet → Haiku có thể drop accuracy **15-20%**.
- Đổi từ Sonnet → Opus có thể tăng accuracy **5-10%**.

### 9.3 Pattern 1: LLM-in-the-middle Pipeline — LLM chiếm ~22%

```
[Router] → [Linker] → [Generator] → [Validator] → [Executor]
  code       code        LLM           code          code
```

LLM chỉ làm **1 việc duy nhất**: sinh SQL từ Context Package đã chuẩn bị sẵn.

| Thành phần | % đóng góp | Ghi chú |
|---|---|---|
| **Semantic Layer** | ~25-30% | Metric definitions quyết định đúng/sai logic |
| **Schema Linker** | ~25-30% | Retrieval miss = fail bất kể LLM nào |
| **LLM model quality** | **~20-25%** | Chỉ "fill-in-the-blank" từ context sẵn |
| **Few-shot examples** | ~8-10% | Hướng dẫn SQL pattern |
| **Validator + Self-correction** | ~10-15% | Bắt lỗi + retry tăng thêm ~10% accuracy |

**Tại sao LLM chỉ chiếm ~22%?**
- **Trước LLM**: Linker đã resolve xong bảng, JOIN, metric, enum, sensitive columns.
- **Sau LLM**: Validator bắt hallucination (bịa column, thiếu LIMIT, DML).
- LLM chỉ cần ghép các mảnh thành SQL syntax đúng.
- Đổi Sonnet → Haiku chỉ drop **5-8%** (context tốt bù model yếu).
- Đổi Sonnet → Opus chỉ tăng **2-4%** (ceiling bị giới hạn bởi retrieval quality).

### 9.4 Pattern 3: Adaptive Router + Tiered Agents — LLM chiếm ~33%

```
User Question → [Router] → L1: Fast Path   (LLM only,       ~40% queries)
                          → L2-L3: Standard (full pipeline,  ~45% queries)
                          → L4: Deep Path   (full + reasoning, ~15% queries)
```

LLM contribution **thay đổi theo tier**:

| Tier | % queries | LLM đóng góp trong tier | Giải thích |
|---|---|---|---|
| **L1 Fast** | ~40% | **~50-55%** | Giống Pattern 2 — skip validation, LLM tự xử |
| **L2-L3 Standard** | ~45% | **~20-25%** | Giống Pattern 1 — full pipeline bọc LLM |
| **L4 Deep** | ~15% | **~30-35%** | Pipeline + extended reasoning, LLM phải suy luận phức tạp hơn |

**Weighted average cho toàn hệ thống:**

| Thành phần | % đóng góp (weighted) | Tính toán |
|---|---|---|
| **Router accuracy** | ~12-15% | Router sai tier = sai pipeline = sai kết quả |
| **Semantic Layer** | ~18-22% | Vẫn quan trọng nhưng L1 bypass một phần |
| **Schema Linker** | ~18-22% | Chỉ dùng cho L2+ |
| **LLM model quality** | **~30-35%** | Weighted: 40%×55% + 45%×22% + 15%×32% ≈ 33% |
| **Few-shot + Prompt** | ~8-10% | |
| **Validator** | ~5-8% | Chỉ chạy cho L2+ |

### 9.5 Tổng hợp so sánh

```
                      LLM quality contribution

Pattern 2 (Single Agent)     ████████████████████████████  ~50%
Pattern 3 (Adaptive Router)  ██████████████████            ~33%
Pattern 1 (LLM-in-middle)   ████████████                  ~22%
```

| | Pattern 2: RAG Single Agent | Pattern 1: LLM-in-the-middle | Pattern 3: Adaptive Router |
|---|---|---|---|
| **LLM chiếm** | **~50%** | **~22%** | **~33%** |
| **Code/Data chiếm** | **~50%** | **~78%** | **~67%** |
| Đổi LLM tốt hơn → gain | +5-10% accuracy | +2-4% accuracy | +3-6% accuracy |
| Đổi LLM kém hơn → loss | -15-20% accuracy | -5-8% accuracy | -8-12% accuracy |
| Sensitivity to LLM | **Rất cao** | **Thấp** | **Trung bình** |

### 9.6 Hàm ý chiến lược

**Scenario analysis — LLM tốt vs. Engineering tốt:**

```
Scenario A: LLM tốt (Opus) + Schema Linker tệ     → Accuracy ~50-60%
Scenario B: LLM trung bình (Sonnet) + Schema Linker tốt → Accuracy ~80-85%
Scenario C: LLM tốt + Schema Linker tốt            → Accuracy ~88-92%
```

**Ma trận quyết định:**

| Nếu muốn... | Nên chọn... | Lý do |
|---|---|---|
| Accuracy cao nhất với LLM trung bình | Pattern 1 | Code bù cho LLM yếu |
| Prototype nhanh, chấp nhận phụ thuộc LLM | Pattern 2 | Ít code, LLM gánh team |
| Balance latency + accuracy ở production | Pattern 3 | Query đơn giản nhanh, phức tạp mới dùng full pipeline |
| Giảm rủi ro khi LLM provider thay đổi/tăng giá | Pattern 1 | LLM là pluggable component, thay mà không ảnh hưởng nhiều |

**Khuyến nghị phân bổ effort (100 giờ):**

| Thành phần | Pattern 2 | Pattern 1 | Pattern 3 |
|---|---|---|---|
| Semantic Layer | 15h | **40h** | 30h |
| Schema Linker / RAG | 20h | **30h** | 25h |
| Prompt engineering | **35h** | 15h | 20h |
| Few-shot curation | **20h** | 10h | 15h |
| Router logic | 0h | 0h | **10h** |
| Validator | 0h | 5h | 0h |
| **Tổng** | 90h code + 10h buffer | 100h | 100h |

**Kết luận:** Lộ trình **Pattern 2 → 1 → 3** cũng phản ánh hành trình **giảm dần phụ thuộc LLM**: bắt đầu lệ thuộc cao (50%) để validate nhanh, dần chuyển effort sang code/data layer (22%), cuối cùng tối ưu adaptive (33%) để đổi lấy tốc độ cho query đơn giản. Đầu tư vào **Semantic Layer + Schema Linker** mang lại ROI cao hơn nhiều so với upgrade LLM model.

---

## 10. SEMANTIC LAYER — YÊU CẦU CHI TIẾT

### 10.1 Tổng quan

Semantic Layer là **nguồn tri thức nghiệp vụ** cho toàn bộ hệ thống. Nó bridge giữa ngôn ngữ business và cấu trúc database. Cần chứa **7 loại thông tin**:

```
┌─────────────────────────────────────────────────────────────────┐
│                      SEMANTIC LAYER                              │
│                                                                  │
│   ① Metric Definitions        ⑤ Sensitive Columns               │
│   ② Dimension Mappings        ⑥ Column Value Enums              │
│   ③ Table/Column Aliases      ⑦ Business Rules & Disambiguation │
│   ④ JOIN Map (dict)                                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 10.2 Chi tiết từng loại thông tin

#### ① Metric Definitions — Business term → SQL expression

**Mục đích:** Đảm bảo "doanh thu" luôn được translate thành cùng 1 SQL expression, bất kể LLM nào generate.

```json
{
  "metrics": {
    "doanh_thu": {
      "aliases": ["revenue", "doanh thu", "doanh số", "total sales", "tổng doanh thu"],
      "sql": "SUM(sales.total_amount)",
      "filters": "sales.status = 'completed'",
      "tables": ["sales"],
      "note": "Chỉ tính giao dịch completed, KHÔNG tính pending/failed/reversed"
    },
    "ti_le_hoan_tien": {
      "aliases": ["refund rate", "tỷ lệ hoàn tiền", "tỷ lệ refund"],
      "sql": "COUNT(refunds.id)::decimal / NULLIF(COUNT(DISTINCT sales.id), 0)",
      "tables": ["sales", "refunds"],
      "join": "LEFT JOIN refunds ON refunds.sale_id = sales.id",
      "note": "LEFT JOIN vì không phải sale nào cũng có refund. NULLIF tránh division by zero"
    },
    "khach_hang_moi": {
      "aliases": ["new customers", "khách hàng mới", "khách mới", "onboarded"],
      "sql": "COUNT(*)",
      "tables": ["customers"],
      "filters": "customers.created_at IN <period>",
      "note": "Tính theo created_at, KHÔNG phải kyc_status"
    },
    "so_du_tai_khoan": {
      "aliases": ["account balance", "số dư", "balance", "tổng số dư"],
      "sql": "accounts.balance",
      "tables": ["accounts"],
      "note": "balance là snapshot hiện tại, KHÔNG phải SUM(transactions)"
    },
    "so_giao_dich": {
      "aliases": ["transaction count", "số giao dịch", "số lượng giao dịch"],
      "sql": "COUNT(sales.id)",
      "tables": ["sales"],
      "filters": "sales.status = 'completed'",
      "note": "Mặc định đếm sales. Nếu user nói 'chuyển khoản' thì đếm transfers"
    },
    "gia_tri_trung_binh": {
      "aliases": ["average transaction", "giá trị trung bình", "avg transaction value", "ATV"],
      "sql": "AVG(sales.total_amount)",
      "tables": ["sales"],
      "filters": "sales.status = 'completed'"
    }
  }
}
```

**Tại sao quan trọng:** Nếu không có metric definition, LLM có thể sinh:
- `SUM(sales.total_amount)` (thiếu WHERE status = 'completed') → đếm cả giao dịch fail
- `SUM(sales.amount)` → column không tồn tại (hallucination)
- `COUNT(sales.*)` → hiểu sai "doanh thu" thành "số lượng"

#### ② Dimension Mappings — Time/category expressions → SQL filters

**Mục đích:** Standardize cách diễn đạt thời gian và phân loại trong tiếng Việt/Anh.

```json
{
  "dimensions": {
    "time": {
      "tháng trước": {
        "sql_start": "DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')",
        "sql_end": "DATE_TRUNC('month', CURRENT_DATE)",
        "pattern": "<time_column> >= {start} AND <time_column> < {end}"
      },
      "quý trước": {
        "sql_start": "DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '1 quarter')",
        "sql_end": "DATE_TRUNC('quarter', CURRENT_DATE)",
        "pattern": "<time_column> >= {start} AND <time_column> < {end}"
      },
      "năm nay": {
        "sql_start": "DATE_TRUNC('year', CURRENT_DATE)",
        "sql_end": "CURRENT_DATE",
        "pattern": "<time_column> >= {start} AND <time_column> <= {end}"
      },
      "7 ngày gần nhất": {
        "sql_start": "CURRENT_DATE - INTERVAL '7 days'",
        "sql_end": "CURRENT_DATE",
        "pattern": "<time_column> >= {start}"
      },
      "hôm nay": {
        "sql_start": "CURRENT_DATE",
        "sql_end": "CURRENT_DATE + INTERVAL '1 day'",
        "pattern": "<time_column> >= {start} AND <time_column> < {end}"
      }
    },
    "default_time_column_per_table": {
      "sales": "sale_time",
      "customers": "created_at",
      "accounts": "opened_at",
      "transfers": "transferred_at",
      "refunds": "refunded_at",
      "employees": "hired_at"
    }
  }
}
```

**Tại sao quan trọng:** "Tháng trước" có thể hiểu là:
- Calendar month trước (March → February) ← **đúng**
- 30 ngày gần nhất ← sai
- Khoảng từ ngày 1 đến 30 tháng trước ← mơ hồ

#### ③ Table/Column Aliases — Vietnamese terms → schema names

**Mục đích:** Map ngôn ngữ tự nhiên tiếng Việt vào tên bảng/cột trong database.

```json
{
  "aliases": {
    "tables": {
      "chi nhánh": "branches",
      "nhân viên": "employees",
      "khách hàng": "customers",
      "tài khoản": "accounts",
      "thẻ": "cards",
      "đơn vị chấp nhận thẻ": "merchants",
      "cửa hàng": "merchants",
      "máy POS": "terminals",
      "sản phẩm": "products",
      "giao dịch": "sales",
      "giao dịch bán hàng": "sales",
      "hoàn tiền": "refunds",
      "chuyển khoản": "transfers",
      "sao kê": "statements",
      "nhật ký": "audit_logs"
    },
    "columns": {
      "tên": ["*.name", "*.first_name", "*.last_name"],
      "trạng thái": ["*.status", "customers.kyc_status"],
      "ngày tạo": ["*.created_at"],
      "số dư": ["accounts.balance"],
      "loại tài khoản": ["accounts.account_type"],
      "loại thẻ": ["cards.card_type"],
      "mạng thẻ": ["cards.network"],
      "mã danh mục": ["merchants.mcc"]
    }
  }
}
```

#### ④ JOIN Map — Relationship Dictionary

**Mục đích:** Cung cấp lookup table (Python dict) đầy đủ để Linker biết cách nối bảng. **Không phải graph database** — chỉ là JSON/dict mapping FK → PK.

```json
{
  "join_map": {
    "edges": [
      {"from": "employees.branch_id",    "to": "branches.id",    "type": "many-to-one"},
      {"from": "accounts.customer_id",   "to": "customers.id",   "type": "many-to-one"},
      {"from": "cards.account_id",       "to": "accounts.id",    "type": "many-to-one"},
      {"from": "terminals.merchant_id",  "to": "merchants.id",   "type": "many-to-one"},
      {"from": "sales.merchant_id",      "to": "merchants.id",   "type": "many-to-one"},
      {"from": "sales.terminal_id",      "to": "terminals.id",   "type": "many-to-one"},
      {"from": "sales.product_id",       "to": "products.id",    "type": "many-to-one"},
      {"from": "sales.card_id",          "to": "cards.id",       "type": "many-to-one"},
      {"from": "refunds.sale_id",        "to": "sales.id",       "type": "many-to-one"},
      {"from": "transfers.from_account", "to": "accounts.id",    "type": "many-to-one", "role": "sender"},
      {"from": "transfers.to_account",   "to": "accounts.id",    "type": "many-to-one", "role": "receiver"},
      {"from": "statements.account_id",  "to": "accounts.id",    "type": "many-to-one"}
    ],
    "domain_clusters": {
      "customer_profile": {
        "tables": ["customers", "accounts", "cards"],
        "description": "Customer identity, accounts, and card management",
        "use_cases": ["KYC queries", "balance inquiry", "card status", "customer onboarding"]
      },
      "transaction_analytics": {
        "tables": ["sales", "merchants", "terminals", "products", "cards"],
        "description": "Sales transactions and merchant performance",
        "use_cases": ["revenue analysis", "product performance", "merchant ranking", "card network usage"]
      },
      "refund_analysis": {
        "tables": ["refunds", "sales", "merchants"],
        "description": "Refund patterns and merchant quality",
        "use_cases": ["refund rate", "refund reasons", "merchant quality scoring"]
      },
      "transfer_analytics": {
        "tables": ["transfers", "accounts", "customers"],
        "description": "Fund transfers between accounts",
        "use_cases": ["self-transfer detection", "transfer volume", "fraud patterns"]
      },
      "hr_branch": {
        "tables": ["branches", "employees"],
        "description": "Branch operations and HR",
        "use_cases": ["employee count", "branch performance", "hiring trends"]
      },
      "audit_compliance": {
        "tables": ["audit_logs"],
        "description": "System audit trail",
        "use_cases": ["action frequency", "compliance investigation", "user activity"]
      },
      "account_statements": {
        "tables": ["statements", "accounts"],
        "description": "Periodic account statements",
        "use_cases": ["balance changes", "statement frequency"]
      }
    }
  }
}
```

#### ⑤ Sensitive Columns — Danh sách cột phải bảo vệ

**Mục đích:** Ngăn chặn data breach qua SQL query.

```json
{
  "sensitive_columns": {
    "blocked": {
      "description": "KHÔNG BAO GIỜ được xuất hiện trong SELECT hoặc WHERE",
      "columns": ["cards.cvv", "cards.card_number"]
    },
    "masked": {
      "description": "Được phép query nhưng phải mask trong kết quả",
      "rules": {
        "customers.email": "LEFT(email, 3) || '***@' || SPLIT_PART(email, '@', 2)",
        "customers.phone": "'***' || RIGHT(phone, 4)"
      }
    },
    "audit_logged": {
      "description": "Được phép query nhưng phải ghi audit log",
      "columns": ["customers.dob", "accounts.account_number", "accounts.balance"]
    }
  }
}
```

#### ⑥ Column Value Enums — Giá trị hợp lệ cho categorical columns

**Mục đích:** Ngăn LLM bịa giá trị không tồn tại.

```json
{
  "column_enums": {
    "customers.kyc_status": {
      "values": ["unverified", "pending", "verified", "rejected"],
      "description": "KYC verification status",
      "note": "Case-sensitive, lowercase"
    },
    "accounts.account_type": {
      "values": ["checking", "savings", "credit"],
      "description": "Type of bank account"
    },
    "accounts.status": {
      "values": ["open", "closed", "frozen"],
      "description": "Current account status"
    },
    "cards.card_type": {
      "values": ["debit", "credit", "prepaid"],
      "description": "Type of payment card"
    },
    "cards.network": {
      "values": ["VISA", "MasterCard", "AMEX"],
      "description": "Payment network",
      "note": "Case-sensitive: VISA (uppercase), MasterCard (CamelCase)"
    },
    "cards.status": {
      "values": ["active", "blocked", "expired"],
      "description": "Current card status"
    },
    "sales.status": {
      "values": ["completed", "pending", "failed", "reversed"],
      "description": "Transaction status"
    },
    "employees.role": {
      "values": ["teller", "manager", "officer", "analyst"],
      "description": "Job role"
    }
  }
}
```

**Tại sao ⑥ Enums cực kỳ quan trọng:**

```
KHÔNG CÓ ENUM → LLM đoán:
  "Khách hàng đã xác minh" → WHERE kyc_status = 'approved'     ← SAI (không tồn tại)
  "Thẻ VISA"               → WHERE network = 'visa'            ← SAI (phải là 'VISA')
  "Giao dịch thành công"   → WHERE status = 'success'          ← SAI (phải là 'completed')

CÓ ENUM → LLM biết chính xác:
  kyc_status IN ('unverified','pending','verified','rejected')
  → Chắc chắn sinh: WHERE kyc_status = 'verified'

  network IN ('VISA','MasterCard','AMEX')
  → Chắc chắn sinh: WHERE network = 'VISA'
```

#### ⑦ Business Rules & Disambiguation

**Mục đích:** Xử lý các trường hợp mơ hồ và quy tắc nghiệp vụ đặc thù.

```json
{
  "business_rules": [
    {
      "rule": "Doanh thu chỉ tính giao dịch completed",
      "applies_to": "metric:doanh_thu",
      "reason": "pending/failed/reversed không phải revenue thực tế"
    },
    {
      "rule": "Khách hàng mới tính theo created_at, KHÔNG phải kyc_status",
      "applies_to": "metric:khach_hang_moi",
      "reason": "kyc_status='unverified' có thể là khách cũ chưa verify, không phải khách mới"
    },
    {
      "rule": "accounts.balance là snapshot hiện tại",
      "applies_to": "column:accounts.balance",
      "reason": "KHÔNG dùng SUM(transactions) để tính balance, vì balance đã là giá trị cập nhật"
    },
    {
      "rule": "Refund rate dùng LEFT JOIN",
      "applies_to": "metric:ti_le_hoan_tien",
      "reason": "INNER JOIN sẽ loại bỏ sales không có refund → tỷ lệ bị sai (luôn = 100%)"
    }
  ],
  "disambiguation": [
    {
      "term": "giao dịch",
      "options": [
        {"meaning": "Sales transactions (POS)", "table": "sales", "default": true},
        {"meaning": "Fund transfers", "table": "transfers", "default": false}
      ],
      "resolution": "Mặc định là sales. Nếu user nói 'chuyển khoản', 'chuyển tiền' → dùng transfers. Nếu mơ hồ → hỏi lại."
    },
    {
      "term": "số lượng",
      "options": [
        {"meaning": "COUNT(*) — đếm số records", "default": true},
        {"meaning": "SUM(quantity) — tổng số lượng sản phẩm", "default": false}
      ],
      "resolution": "Mặc định là COUNT. Nếu context là 'sản phẩm bán được bao nhiêu' → SUM(quantity)."
    },
    {
      "term": "active/inactive",
      "options": [
        {"meaning": "Có giao dịch trong 90 ngày gần nhất", "default": true},
        {"meaning": "accounts.status = 'open'", "default": false}
      ],
      "resolution": "Mặc định là có/không giao dịch. Nếu user hỏi 'trạng thái tài khoản' → dùng accounts.status."
    }
  ]
}
```

### 10.3 Semantic Layer — Tóm tắt

| # | Loại thông tin | Nguồn | Tần suất cập nhật |
|---|---------------|-------|-------------------|
| ① | Metric Definitions | Domain expert define | Khi thêm metric mới hoặc logic thay đổi |
| ② | Dimension Mappings | Domain expert define | Ít thay đổi (time patterns ổn định) |
| ③ | Table/Column Aliases | Domain expert define | Khi thêm bảng mới |
| ④ | JOIN Map (dict) | Auto-detect + expert enrich | Khi schema thay đổi (migration) |
| ⑤ | Sensitive Columns | Security/Compliance team | Khi policy thay đổi |
| ⑥ | Column Value Enums | Auto-detect từ DB (DISTINCT) + expert validate | Khi thêm enum value mới |
| ⑦ | Business Rules | Domain expert define | Khi quy tắc nghiệp vụ thay đổi |

**⑥ Column Value Enums có thể semi-auto detect:**

```sql
-- Auto-detect enum values từ DB
SELECT DISTINCT kyc_status FROM customers;      -- → ['unverified','pending','verified','rejected']
SELECT DISTINCT account_type FROM accounts;     -- → ['checking','savings','credit']
SELECT DISTINCT network FROM cards;             -- → ['VISA','MasterCard','AMEX']

-- Chỉ áp dụng cho columns có cardinality thấp (< 20 distinct values)
-- Domain expert review và confirm trước khi đưa vào semantic layer
```

---

*Tài liệu Solution Suggestion v1.3 — Thêm phân tích mức độ phụ thuộc LLM theo Pattern (Section 9)*
*Ngày tạo: 25/03/2026 | Cập nhật: 25/03/2026*
*Phần tiếp theo: [Architecture Design](./architecture_design.md) — Chi tiết thiết kế từng component*
