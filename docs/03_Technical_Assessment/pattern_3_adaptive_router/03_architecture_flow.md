# Luồng Architecture Tổng Thể — Adaptive Router + Tiered Agents

### Pattern 3 | Phase 3 — Production

---

## MỤC LỤC

1. [Kiến trúc tổng thể](#1-kiến-trúc-tổng-thể)
2. [Luồng traffic tổng quan](#2-luồng-traffic-tổng-quan)
3. [Chi tiết luồng từng Tier](#3-chi-tiết-luồng-từng-tier)
4. [Caching Layer](#4-caching-layer)
5. [Monitoring Integration](#5-monitoring-integration)
6. [Router Feedback Loop](#6-router-feedback-loop)
7. [Tier Escalation](#7-tier-escalation)

---

## 1. KIẾN TRÚC TỔNG THỂ

```mermaid
graph TB
    subgraph "CLIENT"
        USER[User — Business Analyst]
        REACT[React + TailwindCSS]
    end

    subgraph "API GATEWAY"
        NGINX[Nginx<br/>Rate Limiting · SSL · Load Balancing]
    end

    subgraph "APPLICATION SERVER"
        FASTAPI[FastAPI<br/>REST API + SSE Streaming]
        REDIS_CHECK{Redis Cache<br/>Hit?}
    end

    subgraph "ADAPTIVE ROUTER"
        HAIKU[Claude Haiku<br/>Classification ~0.3s]
        DISPATCH{Dispatch<br/>by Level}
    end

    subgraph "TIER 1 — FAST PATH (~40%)"
        F_RAG[RAG Context<br/>Retrieval]
        F_SONNET[Claude Sonnet<br/>SQL Generation]
        F_EXEC[Execute SQL]
    end

    subgraph "TIER 2 — STANDARD PATH (~45%)"
        S_LINKER[Schema Linker]
        S_SONNET[Claude Sonnet<br/>SQL Generation]
        S_VALID[Validator]
        S_EXEC[Execute SQL]
        S_RETRY[Self-Correction<br/>Loop]
    end

    subgraph "TIER 3 — DEEP PATH (~15%)"
        D_LINKER[Schema Linker]
        D_OPUS[Claude Opus<br/>Extended Reasoning]
        D_VALID[Validator]
        D_EXEC[Execute SQL]
        D_RETRY[Self-Correction<br/>Loop]
    end

    subgraph "KNOWLEDGE LAYER"
        SEMANTIC[Semantic Layer]
        VECTOR[pgvector<br/>Vector Store]
        EXAMPLES[Example Store]
    end

    subgraph "DATA LAYER"
        PG[(PostgreSQL 18)]
        REDIS[(Redis Cache)]
    end

    subgraph "MONITORING"
        LANGFUSE[Langfuse<br/>LLM Traces + Cost]
        PROM[Prometheus + Grafana<br/>System Metrics]
        ROUTER_LOG[Router Accuracy<br/>Tracking]
    end

    USER --> REACT --> NGINX --> FASTAPI
    FASTAPI --> REDIS_CHECK
    REDIS_CHECK -->|HIT| FASTAPI
    REDIS_CHECK -->|MISS| HAIKU

    HAIKU --> DISPATCH
    DISPATCH -->|L1| F_RAG
    DISPATCH -->|L2-L3| S_LINKER
    DISPATCH -->|L4| D_LINKER

    F_RAG --> VECTOR
    F_RAG --> SEMANTIC
    F_RAG --> EXAMPLES
    F_RAG --> F_SONNET --> F_EXEC

    S_LINKER --> VECTOR
    S_LINKER --> SEMANTIC
    S_LINKER --> EXAMPLES
    S_LINKER --> S_SONNET --> S_VALID
    S_VALID -->|PASS| S_EXEC
    S_VALID -->|FAIL| S_RETRY --> S_SONNET

    D_LINKER --> VECTOR
    D_LINKER --> SEMANTIC
    D_LINKER --> EXAMPLES
    D_LINKER --> D_OPUS --> D_VALID
    D_VALID -->|PASS| D_EXEC
    D_VALID -->|FAIL| D_RETRY --> D_OPUS

    F_EXEC --> PG
    S_EXEC --> PG
    D_EXEC --> PG

    F_EXEC --> REDIS
    S_EXEC --> REDIS
    D_EXEC --> REDIS

    HAIKU --> LANGFUSE
    F_SONNET --> LANGFUSE
    S_SONNET --> LANGFUSE
    D_OPUS --> LANGFUSE
    HAIKU --> ROUTER_LOG
    FASTAPI --> PROM
```

---

## 2. LUỒNG TRAFFIC TỔNG QUAN

Mọi request đều đi qua cùng một entry point, sau đó fan-out theo classification của Router:

```mermaid
graph LR
    subgraph "Entry (chung)"
        A[User] --> B[Nginx]
        B --> C[FastAPI]
        C --> D{Redis<br/>Cache?}
        D -->|HIT| Z[Response]
        D -->|MISS| E[Adaptive Router<br/>Haiku]
    end

    subgraph "Fan-out (theo tier)"
        E -->|"L1 (~40%)"| F[Fast Path]
        E -->|"L2-L3 (~45%)"| G[Standard Path]
        E -->|"L4 (~15%)"| H[Deep Path]
    end

    subgraph "Convergence (chung)"
        F --> I[Cache Result<br/>in Redis]
        G --> I
        H --> I
        I --> Z
    end
```

**Các bước chung cho mọi request:**

| Bước | Component | Mô tả | Latency |
|------|-----------|-------|---------|
| 1 | Nginx | Nhận request, rate limit check, forward đến FastAPI | ~1-5ms |
| 2 | FastAPI | Parse request, authenticate, extract question | ~1-5ms |
| 3 | Redis | Kiểm tra cache — nếu HIT, trả kết quả ngay | ~1-5ms |
| 4 | Router (Haiku) | Classify câu hỏi → dispatch đến tier | ~300ms |
| 5 | Tier processing | Xử lý theo tier tương ứng | 2-15s (tùy tier) |
| 6 | Redis | Cache kết quả với TTL | ~1-5ms |
| 7 | FastAPI | Format response, stream về client | ~1-5ms |

---

## 3. CHI TIẾT LUỒNG TỪNG TIER

### 3.1 Fast Path — Luồng nội bộ

```mermaid
graph TD
    START[Router dispatches L1] --> RAG[RAG Context Retrieval]

    RAG --> VS["Vector Search<br/>Tìm tables liên quan (top_k=2)"]
    RAG --> SL["Semantic Layer Lookup<br/>Resolve business terms → SQL"]
    RAG --> EX["Example Store<br/>Tìm few-shot examples tương tự"]

    VS --> BUILD[Build Prompt]
    SL --> BUILD
    EX --> BUILD

    BUILD --> SONNET["Claude Sonnet<br/>1 lần gọi duy nhất"]
    SONNET --> SQL[Generated SQL]
    SQL --> EXEC["Execute SQL<br/>PostgreSQL"]
    EXEC -->|SUCCESS| RESULT[Return Result]
    EXEC -->|ERROR| ESCALATE["Escalate → Standard Path"]
```

**Đặc điểm:**
- Không có Validator → SQL đi thẳng vào Executor
- Nếu Executor trả error → **escalate lên Standard Path** (không retry trong Fast Path)
- Tổng latency: ~2-3s (RAG ~0.5s + Sonnet ~1.5-2s + Execute ~0.3s)

### 3.2 Standard Path — Luồng nội bộ

```mermaid
graph TD
    START[Router dispatches L2-L3] --> LINKER[Schema Linker]

    LINKER --> VS["Vector Search (top_k=3)"]
    LINKER --> CLUSTER["Domain Cluster Lookup"]
    LINKER --> METRIC["Metric Resolution"]
    LINKER --> JOIN["JOIN Path Detection"]
    LINKER --> FEW["Few-shot Example Retrieval"]

    VS --> CTX[Context Package — JSON]
    CLUSTER --> CTX
    METRIC --> CTX
    JOIN --> CTX
    FEW --> CTX

    CTX --> SONNET["Claude Sonnet — SQL Generation"]
    SONNET --> SQL[Generated SQL]
    SQL --> VALID{Validator}

    VALID -->|"PASS"| EXEC["Execute SQL"]
    VALID -->|"FAIL<br/>attempt < 3"| FEEDBACK["Build Error Feedback<br/>- Error type<br/>- Error message<br/>- Hint"]
    FEEDBACK --> SONNET

    VALID -->|"FAIL<br/>attempt >= 3"| ERR_USER["Return Error to User"]

    EXEC -->|SUCCESS| RESULT["Return Result"]
    EXEC -->|"ERROR<br/>attempt < 3"| RT_FEEDBACK["Build Runtime Feedback<br/>- PostgreSQL error<br/>- Execution context"]
    RT_FEEDBACK --> SONNET
    EXEC -->|"ERROR<br/>attempt >= 3"| ERR_USER
```

**Đặc điểm:**
- Full pipeline giống Pattern 1
- Validator bắt lỗi trước khi execute → tiết kiệm DB resources
- Self-Correction Loop tối đa 3 attempts
- Tổng latency: ~5-8s (Linker ~1s + Sonnet ~2-3s + Validate ~0.5s + Execute ~0.5s, x1-3 attempts)

### 3.3 Deep Path — Luồng nội bộ

```mermaid
graph TD
    START[Router dispatches L4] --> LINKER["Schema Linker<br/>(extended context)"]

    LINKER --> VS["Vector Search (top_k=5)"]
    LINKER --> CLUSTER["Domain Cluster Lookup<br/>(multiple clusters)"]
    LINKER --> METRIC["Metric Resolution"]
    LINKER --> JOIN["JOIN Path Detection<br/>(deep traversal)"]
    LINKER --> FEW["Few-shot Examples<br/>(complex patterns only)"]

    VS --> CTX["Extended Context Package"]
    CLUSTER --> CTX
    METRIC --> CTX
    JOIN --> CTX
    FEW --> CTX

    CTX --> COT["Build Chain-of-Thought Prompt<br/>- Step-by-step reasoning instructions<br/>- Complex SQL patterns reference<br/>- Extended context"]

    COT --> OPUS["Claude Opus — Extended Reasoning<br/>- Suy nghĩ từng bước<br/>- Xác định SQL strategy<br/>- Sinh SQL cuối cùng"]

    OPUS --> SQL[Generated SQL]
    SQL --> VALID{Validator<br/>+ Extended Rules}

    VALID -->|"PASS"| EXEC["Execute SQL<br/>(timeout 60s)"]
    VALID -->|"FAIL<br/>attempt < 3"| FEEDBACK["Build Detailed Feedback<br/>- Error analysis<br/>- Reasoning trace<br/>- Suggested fix"]
    FEEDBACK --> OPUS

    VALID -->|"FAIL<br/>attempt >= 3"| ERR_USER["Return Error to User"]

    EXEC -->|SUCCESS| RESULT["Return Result"]
    EXEC -->|"ERROR<br/>attempt < 3"| RT_FEEDBACK["Build Runtime Feedback<br/>+ Execution plan analysis"]
    RT_FEEDBACK --> OPUS
    EXEC -->|"ERROR<br/>attempt >= 3"| ERR_USER
```

**Đặc điểm khác biệt so với Standard Path:**
- Schema Linker retrieve nhiều context hơn (`top_k=5` thay vì 3)
- Multiple domain clusters (câu hỏi L4 thường span nhiều domains)
- Chain-of-thought prompting cho Opus — yêu cầu reasoning trước khi viết SQL
- Validator có thêm rules cho complex patterns (CTE nesting depth, window function syntax)
- Execute timeout dài hơn (60s thay vì 30s)
- Error feedback chi tiết hơn — bao gồm reasoning trace
- Tổng latency: ~10-15s

---

## 4. CACHING LAYER

Redis đóng vai trò cache layer quan trọng, giảm LLM calls và cải thiện latency cho repeated queries.

### 4.1 Cache Flow

```mermaid
graph TD
    Q[User Question] --> NORM["Normalize Question<br/>- Lowercase<br/>- Remove extra spaces<br/>- Standardize punctuation"]

    NORM --> HASH["Compute Cache Key<br/>SHA256(normalized_question + db_version)"]

    HASH --> CHECK{Redis GET}

    CHECK -->|"HIT<br/>(TTL chưa hết)"| CACHED["Return Cached Result<br/>Latency: ~5ms"]

    CHECK -->|"MISS"| PIPELINE["Process through<br/>Router → Tier → Execute"]

    PIPELINE --> RESULT[SQL + Data + Metadata]
    RESULT --> STORE["Redis SET<br/>Key: hash<br/>Value: {sql, data, metadata}<br/>TTL: 1 hour"]
    STORE --> RETURN["Return Result to User"]
```

### 4.2 Cache Key Design

| Thành phần | Mô tả | Ví dụ |
|-----------|-------|-------|
| **Normalized question** | Câu hỏi sau khi normalize | "top 10 merchant doanh thu cao nhất quý trước" |
| **DB version** | Version hash của data (thay đổi khi data update) | "v20260325" |
| **Cache key** | SHA256 hash | `SHA256("top 10 merchant...||v20260325")` |

**Tại sao cần DB version?** Khi data trong PostgreSQL thay đổi (ETL chạy hàng đêm), cache cũ sẽ invalidate tự động vì DB version thay đổi → cache key khác → cache miss.

### 4.3 Cache Hit Rate dự kiến

| Scenario | Cache hit rate | Lý do |
|----------|---------------|-------|
| Ngày đầu tiên | ~0% | Cache trống |
| Sau 1 tuần | ~20-30% | Các câu hỏi phổ biến bắt đầu lặp lại |
| Ổn định | ~30-40% | Business users hỏi lặp các báo cáo quen thuộc |

---

## 5. MONITORING INTEGRATION

Mọi bước trong pipeline đều được log để monitoring và debug.

### 5.1 Tổng quan Monitoring Flow

```mermaid
graph TB
    subgraph "Request Lifecycle"
        REQ[Request In] --> ROUTER[Router]
        ROUTER --> TIER[Tier Processing]
        TIER --> RESP[Response Out]
    end

    subgraph "Langfuse — LLM Metrics"
        L_ROUTER["Router trace<br/>- Model: Haiku<br/>- Latency: 0.3s<br/>- Cost: $0.0003<br/>- Classification: L2"]
        L_GEN["Generator trace<br/>- Model: Sonnet/Opus<br/>- Latency: 2-8s<br/>- Cost: $0.003-0.05<br/>- Prompt version: v12"]
        L_QUALITY["Quality score<br/>- SQL valid: true<br/>- Execute success: true<br/>- User feedback: positive"]
    end

    subgraph "Prometheus + Grafana — System Metrics"
        P_LATENCY["API latency<br/>histogram (p50/p95/p99)"]
        P_ERROR["Error rate<br/>counter by type"]
        P_THROUGHPUT["Throughput<br/>requests/sec"]
        P_RESOURCE["Resource usage<br/>CPU / Memory / DB connections"]
        P_CACHE["Cache hit rate<br/>gauge"]
    end

    subgraph "Router Accuracy — Custom"
        R_ACC["Classification accuracy"]
        R_ESC["Escalation rate"]
        R_CONF["Confidence distribution"]
    end

    ROUTER --> L_ROUTER
    TIER --> L_GEN
    RESP --> L_QUALITY

    REQ --> P_LATENCY
    REQ --> P_THROUGHPUT
    TIER --> P_ERROR
    TIER --> P_RESOURCE
    REQ --> P_CACHE

    ROUTER --> R_ACC
    TIER --> R_ESC
    ROUTER --> R_CONF
```

### 5.2 Điểm đo cụ thể tại mỗi bước

| Bước | Langfuse log | Prometheus metric |
|------|-------------|-------------------|
| **Nginx receive** | — | `http_requests_total`, `request_duration_seconds` |
| **Redis check** | — | `cache_hit_total`, `cache_miss_total` |
| **Router classify** | Model, latency, cost, classification result | `router_latency_seconds`, `router_classification_total{level}` |
| **Schema Linker** | — | `schema_linker_latency_seconds`, `tables_retrieved_count` |
| **SQL Generator** | Model, prompt, response, latency, cost | `llm_latency_seconds{model}`, `llm_cost_total{model}` |
| **Validator** | — | `validation_pass_total`, `validation_fail_total` |
| **Executor** | — | `sql_execution_seconds`, `sql_error_total{type}` |
| **Self-Correction** | Retry count, error feedback | `retry_count_total{tier}` |

---

## 6. ROUTER FEEDBACK LOOP

Router accuracy quyết định hiệu quả của toàn bộ Pattern 3. Feedback loop giúp cải thiện Router theo thời gian.

### 6.1 Cách đo Router accuracy

```mermaid
graph TD
    subgraph "Runtime (mỗi query)"
        Q[Query vào] --> R["Router classifies: L1"]
        R --> T1["Fast Path processes"]
        T1 --> OUTCOME{"Outcome?"}
        OUTCOME -->|"Success"| LOG1["Log: L1 → Success<br/>Router đúng"]
        OUTCOME -->|"Fail → Escalate"| LOG2["Log: L1 → Escalate to L2<br/>Router có thể sai"]
    end

    subgraph "Retrospective (hàng tuần)"
        LOGS["Aggregated Logs"] --> ANALYSIS["Phân tích:<br/>- Escalation rate per level<br/>- Success rate per level<br/>- Confidence vs actual outcome"]
        ANALYSIS --> DECISION{"Cần adjust?"}
        DECISION -->|"Escalation > 15%"| ADJUST["Adjust Router:<br/>- Update classification prompt<br/>- Tăng confidence threshold<br/>- Thêm examples cho cases sai"]
        DECISION -->|"Escalation < 5%"| OK["Router hoạt động tốt"]
    end

    LOG1 --> LOGS
    LOG2 --> LOGS
```

### 6.2 Metrics cho Feedback Loop

| Metric | Công thức | Target |
|--------|----------|--------|
| **Escalation rate** | Escalated queries / Total queries | < 10% |
| **Downgrade waste** | Queries dùng tier cao nhưng SQL đơn giản / Total queries | < 5% |
| **Router accuracy** | Correctly classified / Total queries | > 85% |
| **Average confidence** | Mean(confidence scores) | > 0.75 |

### 6.3 Cách cải thiện Router

| Vấn đề phát hiện | Hành động | Ví dụ |
|-------------------|----------|-------|
| Quá nhiều L1 escalate lên L2 | Tăng confidence threshold cho L1 (0.7 → 0.8) | Câu hỏi có "theo tháng" bị classify L1 nhưng cần GROUP BY + date |
| Quá nhiều L2 dùng Opus (waste) | Thêm examples cho L2 trong prompt | "Top merchant" bị classify L4 nhưng chỉ cần simple JOIN |
| Confidence thấp liên tục cho 1 loại câu hỏi | Thêm examples cho loại đó vào classification prompt | Câu hỏi so sánh temporal luôn bị low confidence |

---

## 7. TIER ESCALATION

Khi một tier không xử lý được query, hệ thống tự động escalate lên tier cao hơn.

### 7.1 Escalation Flow

```mermaid
graph TD
    subgraph "Fast Path"
        F_START[L1 Query] --> F_SONNET[Sonnet generates SQL]
        F_SONNET --> F_EXEC{Execute}
        F_EXEC -->|SUCCESS| F_OK[Return Result]
        F_EXEC -->|ERROR| F_ESC["Escalate to Standard"]
    end

    subgraph "Standard Path (Escalated)"
        F_ESC --> S_LINKER["Schema Linker<br/>(full context)"]
        S_LINKER --> S_SONNET["Sonnet with<br/>error context"]
        S_SONNET --> S_VALID{Validate}
        S_VALID -->|PASS| S_EXEC{Execute}
        S_VALID -->|"FAIL (3x)"| S_ESC["Escalate to Deep"]
        S_EXEC -->|SUCCESS| S_OK[Return Result]
        S_EXEC -->|"ERROR (3x)"| S_ESC
    end

    subgraph "Deep Path (Escalated)"
        S_ESC --> D_LINKER["Schema Linker<br/>(extended context)"]
        D_LINKER --> D_OPUS["Opus with<br/>full error history"]
        D_OPUS --> D_VALID{Validate}
        D_VALID -->|PASS| D_EXEC{Execute}
        D_VALID -->|"FAIL (3x)"| D_ERR[Return Error to User]
        D_EXEC -->|SUCCESS| D_OK[Return Result]
        D_EXEC -->|"ERROR (3x)"| D_ERR
    end
```

### 7.2 Escalation Rules

| Trigger | Từ tier | Đến tier | Context truyền theo |
|---------|---------|----------|---------------------|
| Execute error ở Fast Path | Tier 1 | Tier 2 | Original question + failed SQL + error message |
| 3x validate/execute fail ở Standard | Tier 2 | Tier 3 | Original question + 3 failed SQLs + error history |
| 3x validate/execute fail ở Deep | Tier 3 | — | Return error to user |

**Nguyên tắc quan trọng:**
- Escalation **không quay lại** — chỉ đi lên (L1 → L2 → L3, không bao giờ L3 → L1)
- Mỗi lần escalate, tier mới nhận **toàn bộ error context** từ tier trước — giúp LLM tránh lặp lỗi
- Tối đa **2 lần escalate** cho 1 query (L1 → L2 → L3 → error nếu vẫn fail)
- Escalation được log cho Router feedback loop — Router sẽ học từ các case bị escalate

### 7.3 Tổng latency worst case

| Scenario | Flow | Tổng latency |
|----------|------|-------------|
| Best case (L1, cache hit) | Redis → Return | ~5ms |
| Normal (L1, no cache) | Router → Fast → Execute | ~2.5-3.5s |
| Normal (L2, no cache) | Router → Standard → Execute | ~5.5-8.5s |
| Normal (L4, no cache) | Router → Deep → Execute | ~10.5-15.5s |
| Worst case (L1 → escalate L2 → L3) | Router → Fast fail → Standard fail → Deep → Execute | ~25-30s |

**Worst case ~30s** là chấp nhận được vì:
- Xảy ra rất hiếm (< 1% queries)
- User vẫn nhận feedback qua SSE streaming ("Đang xử lý...", "Đang thử lại...")
- Tốt hơn trả kết quả sai
