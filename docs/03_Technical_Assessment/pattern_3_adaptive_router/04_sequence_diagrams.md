# Sequence Diagrams — Adaptive Router + Tiered Agents

### Pattern 3 | Phase 3 — Production

---

## MỤC LỤC

1. [E2E Happy Path — Fast Path (L1)](#1-e2e-happy-path--fast-path-l1)
2. [E2E Happy Path — Standard Path (L2-L3)](#2-e2e-happy-path--standard-path-l2-l3)
3. [E2E Happy Path — Deep Path (L4)](#3-e2e-happy-path--deep-path-l4)
4. [Cache Hit Flow](#4-cache-hit-flow)
5. [Tier Escalation (Fallback)](#5-tier-escalation-fallback)
6. [Router Classification Detail](#6-router-classification-detail)
7. [Monitoring & Feedback Loop](#7-monitoring--feedback-loop)

---

## 1. E2E HAPPY PATH — FAST PATH (L1)

**Scenario:** User hỏi "Có bao nhiêu khách hàng active?" — câu hỏi đơn giản, chỉ cần `SELECT COUNT(*) FROM customers WHERE status = 'active'`.

**Tổng latency:** ~2.5-3.5s

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Nginx
    participant API as FastAPI
    participant Redis
    participant Router as Router (Haiku)
    participant RAG as RAG Context
    participant VStore as Vector Store
    participant Sonnet as Claude Sonnet
    participant PG as PostgreSQL

    User->>Nginx: POST /api/query<br/>"Có bao nhiêu khách hàng active?"
    Nginx->>API: Forward request (rate limit OK)

    API->>Redis: GET cache_key(normalized_question)
    Redis-->>API: MISS

    API->>Router: Classify question
    Note over Router: Haiku phân tích:<br/>- 1 bảng (customers)<br/>- Simple aggregate (COUNT)<br/>- Không cần JOIN
    Router-->>API: {level: "L1", confidence: 0.92}
    Note over API: Dispatch → Fast Path

    API->>RAG: Retrieve context cho "khách hàng active"
    RAG->>VStore: Vector search (top_k=2)
    VStore-->>RAG: [customers table schema]
    Note over RAG: Semantic layer: "active" → status = 'active'
    RAG-->>API: Context Package

    API->>Sonnet: Generate SQL with context
    Note over Sonnet: Prompt: schema + metric + examples<br/>→ SELECT COUNT(*) FROM customers<br/>WHERE status = 'active'
    Sonnet-->>API: SQL string

    Note over API: Fast Path: KHÔNG qua Validator

    API->>PG: Execute SQL (timeout 30s)
    PG-->>API: [{count: 1847}]

    API->>Redis: SET cache_key → result (TTL: 1h)

    API-->>Nginx: Response JSON
    Nginx-->>User: {sql: "SELECT COUNT(*)...", data: [{count: 1847}]}

    Note over User, PG: Tổng latency: ~2.5-3.5s<br/>Router: 0.3s | RAG: 0.5s | Sonnet: 1.5-2s | Execute: 0.2s
```

---

## 2. E2E HAPPY PATH — STANDARD PATH (L2-L3)

**Scenario:** User hỏi "Top 10 merchant có doanh thu cao nhất quý trước?" — cần JOIN sales + merchants, GROUP BY, ORDER BY, date filter.

**Tổng latency:** ~5.5-8.5s

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI
    participant Redis
    participant Router as Router (Haiku)
    participant Linker as Schema Linker
    participant VStore as Vector Store
    participant Semantic as Semantic Layer
    participant Sonnet as Claude Sonnet
    participant Valid as Validator
    participant PG as PostgreSQL

    User->>API: "Top 10 merchant có doanh thu cao nhất quý trước?"

    API->>Redis: GET cache_key
    Redis-->>API: MISS

    API->>Router: Classify question
    Note over Router: Haiku phân tích:<br/>- 2 bảng (sales, merchants)<br/>- Cần JOIN<br/>- GROUP BY + ORDER BY + LIMIT<br/>- Date filter (quý trước)
    Router-->>API: {level: "L2", confidence: 0.88, reason: "needs JOIN between sales and merchants"}

    Note over API: Dispatch → Standard Path

    API->>Linker: Link schema
    Linker->>VStore: Vector search (top_k=3)
    VStore-->>Linker: [sales, merchants, terminals]
    Linker->>Semantic: Resolve "doanh thu"
    Semantic-->>Linker: SUM(sales.total_amount) WHERE status='completed'
    Linker->>Semantic: Resolve "quý trước"
    Semantic-->>Linker: DATE_TRUNC('quarter', CURRENT_DATE) - INTERVAL '1 quarter'
    Note over Linker: Build Context Package:<br/>tables, JOINs, metrics, examples
    Linker-->>API: Context Package (JSON)

    API->>Sonnet: Generate SQL with Context Package
    Note over Sonnet: Sinh SQL với JOIN + aggregation
    Sonnet-->>API: SQL string

    API->>Valid: Validate SQL
    Note over Valid: ✓ Syntax OK<br/>✓ Tables exist<br/>✓ Columns valid<br/>✓ JOIN FK correct<br/>✓ No unsafe operations
    Valid-->>API: PASS

    API->>PG: Execute SQL (timeout 30s)
    PG-->>API: [{merchant_name: "VinMart", revenue: 523000000}, ...]

    API->>Redis: SET cache_key → result (TTL: 1h)
    API-->>User: Response with SQL + data (10 rows)

    Note over User, PG: Tổng latency: ~5.5-8.5s<br/>Router: 0.3s | Linker: 1s | Sonnet: 2-3s | Validate: 0.5s | Execute: 0.5s
```

---

## 3. E2E HAPPY PATH — DEEP PATH (L4)

**Scenario:** User hỏi "Merchant nào có doanh thu tăng liên tục trong 3 tháng gần nhất?" — cần CTE + window function (LAG) + complex logic.

**Tổng latency:** ~10.5-15.5s

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI
    participant Router as Router (Haiku)
    participant Linker as Schema Linker
    participant VStore as Vector Store
    participant Opus as Claude Opus
    participant Valid as Validator
    participant PG as PostgreSQL

    User->>API: "Merchant nào có doanh thu tăng liên tục 3 tháng gần nhất?"

    API->>Router: Classify question
    Note over Router: Haiku phân tích:<br/>- Cần CTE (monthly aggregation)<br/>- Window function (LAG để so sánh)<br/>- Complex logic (tăng liên tục)<br/>- Multi-step reasoning
    Router-->>API: {level: "L4", confidence: 0.91, reason: "CTE + window function + temporal comparison"}

    Note over API: Dispatch → Deep Path

    API->>Linker: Link schema (extended mode)
    Linker->>VStore: Vector search (top_k=5)
    VStore-->>Linker: [sales, merchants, terminals, products, cards]
    Note over Linker: Extended context:<br/>- More tables for broader context<br/>- Complex JOIN paths<br/>- CTE/window examples from Example Store
    Linker-->>API: Extended Context Package

    API->>Opus: Generate SQL with Chain-of-Thought
    Note over Opus: Chain-of-Thought Reasoning:<br/><br/>Bước 1: Tính doanh thu theo tháng per merchant<br/>→ CTE monthly_revenue<br/><br/>Bước 2: So sánh với tháng trước<br/>→ LAG() OVER (PARTITION BY merchant_id ORDER BY month)<br/><br/>Bước 3: Xác định "tăng liên tục 3 tháng"<br/>→ revenue > prev_revenue cho cả 3 tháng gần nhất<br/><br/>Bước 4: Viết SQL hoàn chỉnh<br/>→ WITH ... SELECT ... HAVING COUNT(*) >= 2
    Opus-->>API: Complex SQL (CTE + window function)

    API->>Valid: Validate SQL (extended rules)
    Note over Valid: ✓ Syntax OK<br/>✓ CTE structure valid<br/>✓ Window function syntax correct<br/>✓ Tables & columns exist<br/>✓ JOIN paths valid
    Valid-->>API: PASS

    API->>PG: Execute SQL (timeout 60s)
    PG-->>API: [{merchant_name: "CircleK", months_growing: 3}, ...]

    API-->>User: Response with SQL + data + reasoning trace

    Note over User, PG: Tổng latency: ~10.5-15.5s<br/>Router: 0.3s | Linker: 1.5s | Opus: 6-10s | Validate: 0.7s | Execute: 1s
```

---

## 4. CACHE HIT FLOW

**Scenario:** User hỏi câu hỏi đã được hỏi trước đó (hoặc câu hỏi tương đương sau normalize).

**Tổng latency:** ~5-10ms

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant Nginx
    participant API as FastAPI
    participant Redis

    User->>Nginx: POST /api/query<br/>"Có bao nhiêu khách hàng active?"
    Nginx->>API: Forward request

    Note over API: Normalize question:<br/>- Lowercase<br/>- Remove extra spaces<br/>- Standardize punctuation<br/><br/>Compute cache key:<br/>SHA256("có bao nhiêu khách hàng active" + "v20260325")

    API->>Redis: GET "sha256:a3f2b1..."
    Redis-->>API: HIT → {sql: "SELECT COUNT(*)...", data: [{count: 1847}], cached_at: "..."}

    Note over API: Cache HIT!<br/>Skip entire pipeline<br/>(Router, LLM, DB — tất cả bị bỏ qua)

    API-->>Nginx: Response JSON (+ cache indicator)
    Nginx-->>User: {sql: "...", data: [...], metadata: {cached: true, original_latency: "2.8s"}}

    Note over User, Redis: Tổng latency: ~5-10ms<br/>Tiết kiệm: Router call + LLM call + DB query
```

**Cache key computation:**

| Bước | Input | Output |
|------|-------|--------|
| 1. Normalize | "Có Bao Nhiêu  khách hàng active? " | "có bao nhiêu khách hàng active" |
| 2. Append DB version | + "v20260325" | "có bao nhiêu khách hàng active\|\|v20260325" |
| 3. Hash | SHA256(...) | "sha256:a3f2b1c4d5e6..." |

**Cache invalidation:**
- TTL: 1 giờ (tự động expire)
- DB version thay đổi (ETL chạy) → tất cả cache key thay đổi → auto miss
- Manual flush khi cần (admin API)

---

## 5. TIER ESCALATION (FALLBACK)

**Scenario:** Router classify câu hỏi là L1, nhưng Fast Path generate SQL sai → Escalate lên Standard Path → xử lý thành công.

**Ví dụ:** "Doanh thu trung bình theo terminal" — Router nghĩ đơn giản (AVG), nhưng thực tế cần JOIN sales + terminals.

```mermaid
sequenceDiagram
    autonumber
    actor User
    participant API as FastAPI
    participant Router as Router (Haiku)
    participant RAG as RAG Context
    participant Sonnet1 as Sonnet (Fast Path)
    participant PG as PostgreSQL
    participant Linker as Schema Linker
    participant Sonnet2 as Sonnet (Standard)
    participant Valid as Validator
    participant Langfuse

    User->>API: "Doanh thu trung bình theo terminal"

    API->>Router: Classify
    Router-->>API: {level: "L1", confidence: 0.72}
    Note over API: Confidence >= 0.7 → dispatch L1

    rect rgb(255, 230, 230)
        Note over API, PG: FAST PATH — sẽ FAIL
        API->>RAG: Retrieve context
        RAG-->>API: Context (nhưng thiếu JOIN path)
        API->>Sonnet1: Generate SQL
        Sonnet1-->>API: SELECT AVG(total_amount) FROM sales
        Note over API: Fast Path: skip Validator
        API->>PG: Execute SQL
        PG-->>API: Result — nhưng không group by terminal!
        Note over API: SQL chạy được nhưng sai logic<br/>(không có GROUP BY terminal)<br/>Phát hiện qua heuristic check:<br/>câu hỏi có "theo terminal"<br/>nhưng SQL không có terminal table
        API->>Langfuse: Log: L1 → Escalate (logic error)
    end

    rect rgb(230, 255, 230)
        Note over API, PG: STANDARD PATH — ESCALATION
        API->>Linker: Full schema linking
        Note over Linker: Vector search tìm thấy:<br/>sales + terminals cần JOIN
        Linker-->>API: Context Package (with JOIN paths)

        API->>Sonnet2: Generate SQL with full context + previous error
        Note over Sonnet2: Context bao gồm:<br/>- Full schema + JOIN paths<br/>- Previous failed SQL<br/>- Error: "missing GROUP BY terminal"
        Sonnet2-->>API: SELECT t.name, AVG(s.total_amount)<br/>FROM sales s JOIN terminals t<br/>ON s.terminal_id = t.id<br/>GROUP BY t.name

        API->>Valid: Validate SQL
        Valid-->>API: PASS ✓

        API->>PG: Execute SQL
        PG-->>API: [{terminal: "POS-001", avg_revenue: 125000}, ...]
    end

    API-->>User: Response (correct result)
    API->>Langfuse: Log: Escalation L1→L2 successful

    Note over User, Langfuse: Tổng latency: ~8-10s (Fast fail: ~3s + Standard: ~5-7s)<br/>Chậm hơn nếu Router classify đúng L2 từ đầu (~5-8s)<br/>Nhưng vẫn tốt hơn trả kết quả SAI
```

**Key takeaway:** Escalation tốn thêm latency nhưng đảm bảo accuracy. Router feedback loop sẽ học từ case này: câu hỏi có "theo [entity]" → có thể cần JOIN → nên classify L2+.

---

## 6. ROUTER CLASSIFICATION DETAIL

**Scenario:** Chi tiết cách Router (Haiku) classify một câu hỏi.

### 6.1 Normal Classification (High Confidence)

```mermaid
sequenceDiagram
    autonumber
    participant API as FastAPI
    participant Haiku as Claude Haiku

    API->>Haiku: Classification Request
    Note over API, Haiku: System prompt:<br/>"Phân loại câu hỏi SQL theo 4 levels:<br/>L1 Simple: 1-2 bảng, SELECT/WHERE/GROUP BY<br/>L2 Join: 2-3 bảng, JOIN, subquery đơn giản<br/>L3 Advanced: CTE, window function<br/>L4 Complex: self-join, correlated subquery"<br/><br/>User question:<br/>"Top 10 merchant có doanh thu cao nhất quý trước?"

    Haiku-->>API: Classification Response
    Note over API, Haiku: {<br/>  "level": "L2",<br/>  "confidence": 0.85,<br/>  "reason": "Cần JOIN sales + merchants,<br/>  GROUP BY merchant, ORDER BY SUM,<br/>  date filter cho quý trước",<br/>  "estimated_tables": ["sales", "merchants"],<br/>  "sql_features": ["JOIN", "GROUP BY", "ORDER BY", "LIMIT"]<br/>}

    Note over API: confidence 0.85 >= 0.7<br/>→ Dispatch to Standard Path (L2)
```

### 6.2 Low Confidence — Fallback to Standard

```mermaid
sequenceDiagram
    autonumber
    participant API as FastAPI
    participant Haiku as Claude Haiku

    API->>Haiku: Classification Request
    Note over API, Haiku: User question:<br/>"Tìm pattern bất thường trong giao dịch<br/>của khách hàng VIP tháng trước"

    Haiku-->>API: Classification Response
    Note over API, Haiku: {<br/>  "level": "L3",<br/>  "confidence": 0.55,<br/>  "reason": "Không rõ 'pattern bất thường'<br/>  cần SQL feature nào — có thể cần<br/>  window function hoặc statistical function,<br/>  hoặc chỉ cần WHERE filter"<br/>}

    Note over API: confidence 0.55 < 0.7<br/>→ DEFAULT to Standard Path (safe choice)<br/>Không dùng L3 vì không chắc chắn

    API->>API: Log: low confidence classification<br/>→ sẽ review trong feedback loop
```

### 6.3 Router Timeout — Fallback

```mermaid
sequenceDiagram
    autonumber
    participant API as FastAPI
    participant Haiku as Claude Haiku

    API->>Haiku: Classification Request
    Note over Haiku: Processing...
    Note over API: Timeout: 1s

    Haiku--xAPI: (no response within 1s)

    Note over API: Router timeout!<br/>→ DEFAULT to Standard Path<br/>→ Log timeout event

    API->>API: Dispatch to Standard Path<br/>Log: router_timeout
```

---

## 7. MONITORING & FEEDBACK LOOP

**Scenario:** Hệ thống thu thập dữ liệu từ mỗi query để phân tích và cải thiện Router.

```mermaid
sequenceDiagram
    autonumber
    participant API as FastAPI
    participant Router as Router
    participant Tier as Tier Processing
    participant Langfuse
    participant Prometheus as Prometheus
    participant Grafana
    participant RouterLog as Router Accuracy DB
    participant Analyst as Data Analyst / Automated Job

    rect rgb(240, 248, 255)
        Note over API, RouterLog: Mỗi query — Runtime logging
        API->>Router: Classify query
        Router-->>API: {level: L2, confidence: 0.88}
        API->>Langfuse: Log router trace<br/>{model: haiku, latency: 0.28s, cost: $0.0003}
        API->>Prometheus: router_classification_total{level="L2"} ++
        API->>RouterLog: INSERT {query_id, level: L2, confidence: 0.88}

        API->>Tier: Process in Standard Path
        Tier-->>API: Result (success, latency: 6.2s)
        API->>Langfuse: Log generation trace<br/>{model: sonnet, latency: 2.8s, attempts: 1}
        API->>Prometheus: request_duration_seconds 6.2
        API->>RouterLog: UPDATE {query_id, outcome: success, actual_tier: L2}
    end

    rect rgb(255, 248, 240)
        Note over Analyst, RouterLog: Hàng tuần — Retrospective analysis
        Analyst->>RouterLog: Query aggregated metrics
        RouterLog-->>Analyst: Metrics:<br/>- Escalation rate: 12% (target < 10%)<br/>- L1 accuracy: 82%<br/>- L4 downgrade waste: 3%<br/>- Avg confidence: 0.78

        Note over Analyst: Phân tích:<br/>- Escalation rate cao hơn target<br/>- L1 accuracy cần cải thiện<br/>- Nhiều câu hỏi có "theo [entity]"<br/>  bị classify L1 nhưng cần JOIN

        Analyst->>Router: Adjust classification:<br/>1. Thêm rule: "theo [entity]" → L2+<br/>2. Tăng L1 confidence threshold: 0.7 → 0.75<br/>3. Thêm 5 examples vào classification prompt

        Analyst->>Grafana: Update Router accuracy dashboard
    end

    rect rgb(240, 255, 240)
        Note over Analyst, RouterLog: Kết quả sau tuning
        Analyst->>RouterLog: Query metrics (tuần sau)
        RouterLog-->>Analyst: Metrics cải thiện:<br/>- Escalation rate: 7% ✓<br/>- L1 accuracy: 89% ✓<br/>- Avg confidence: 0.82 ✓
    end
```

**Dashboard metrics trên Grafana:**

| Panel | Metric | Visualization | Mục đích |
|-------|--------|--------------|----------|
| Router Accuracy | % correctly classified per level | Stacked bar chart (daily) | Track Router quality over time |
| Escalation Rate | % queries escalated per tier | Line chart (daily) | Phát hiện khi Router bắt đầu suy giảm |
| Latency by Tier | p50, p95 latency per tier | Heatmap | Phát hiện tier nào bị chậm |
| Cost Breakdown | LLM cost per tier per day | Stacked area chart | Tracking chi phí theo tier |
| Confidence Distribution | Histogram of Router confidence scores | Histogram | Nhiều low confidence = Router cần retune |
| Cache Hit Rate | % cache hits over time | Gauge | Theo dõi hiệu quả cache |
