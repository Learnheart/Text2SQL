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
8. [Multi-Agent Communication & Hallucination](#8-multi-agent-communication--hallucination)
9. [Semantic Layer — Yêu cầu chi tiết](#9-semantic-layer--yêu-cầu-chi-tiết)

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

### 1.2 Approach được đề xuất: **RAG-Augmented Agentic Pipeline**

Sau khi phân tích các approach phổ biến trên thị trường, approach được đề xuất là kết hợp **RAG (Retrieval-Augmented Generation)** với **Multi-Agent Pipeline**:

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
| **④ RAG + Multi-Agent** | Retrieve + chuyên biệt hóa agents + self-correct | **85-92%** | **Có** | Accuracy cao nhất, self-correction bù 15-20%, modular để mở rộng |

**3 lý do chính chọn RAG + Multi-Agent:**

**① Accuracy là ưu tiên số 1 trong domain Banking**
- Sai 1 số trong báo cáo tài chính → hậu quả nghiêm trọng.
- Multi-agent cho phép validate trước khi execute, self-correct khi sai.
- Snowflake đạt 91% accuracy nhờ semantic layer + multi-step pipeline.

**② Schema 14 bảng vừa đủ phức tạp để cần RAG, chưa đủ lớn để cần fine-tuning**
- 14 bảng, 90 columns = quá nhiều để nhồi vào 1 prompt (Direct Prompting).
- Nhưng chưa đủ lớn (100+ bảng) để justify chi phí fine-tuning.
- RAG chỉ retrieve 2-4 bảng liên quan → context gọn, accuracy cao.

**③ Modular architecture dễ iterate trong Phase R&D**
- Thay đổi LLM? → Chỉ sửa SQL Generator agent.
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
║  LAYER 2: AGENT ORCHESTRATION                                    ║
║  Xử lý logic nghiệp vụ chính (P1→P6)                           ║
║  ┌────────┐ ┌──────────┐ ┌───────────┐ ┌─────────┐ ┌────────┐ ║
║  │ Router │→│ Schema   │→│ SQL       │→│Validator│→│Insight │ ║
║  │        │ │ Linker   │ │ Generator │ │         │ │Analyzer│ ║
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

#### LAYER 2: AGENT ORCHESTRATION — Bộ não xử lý

| Component | Sub-problem | Vai trò | Bắt buộc? |
|-----------|-------------|---------|-----------|
| **Router Agent** | P1: Intent | Phân loại câu hỏi: SQL query / clarification / out-of-scope. Dispatch sang agent phù hợp | **Bắt buộc** |
| **Schema Linker Agent** | P2: Schema Linking | Xác định bảng, cột, JOIN paths liên quan. Query vector store + resolve semantic layer | **Bắt buộc** |
| **SQL Generator Agent** | P3: SQL Generation | Nhận context package → build prompt → gọi LLM → parse SQL output | **Bắt buộc** |
| **Validator Agent** | P4: Validation | Kiểm tra syntax, table/column tồn tại, sensitive columns, DML blocking, EXPLAIN cost | **Bắt buộc** |
| **Query Executor** | P5: Execution | Thực thi SQL read-only với timeout, row limit, error handling | **Bắt buộc** |
| **Insight Analyzer** | P6: Presentation | Format kết quả, sinh narrative giải thích, phát hiện anomaly | Nên có |
| **Self-Correction Loop** | P3+P4 | Khi validate fail hoặc execute error → feedback cho Generator retry (max 3 lần) | **Bắt buộc** |

**Luồng xử lý chính:**

```
User Question
     │
     ▼
[Router] ─── Chitchat/Out-of-scope ──→ Trả lời từ chối lịch sự
     │
     │ SQL Query
     ▼
[Schema Linker] ──→ Retrieve relevant tables + metrics + examples
     │
     │ Context Package
     ▼
[SQL Generator] ──→ LLM sinh SQL
     │
     │ Generated SQL
     ▼
[Validator] ──→ FAIL? ──→ Error feedback ──→ [SQL Generator] (retry, max 3)
     │
     │ PASS
     ▼
[Executor] ──→ ERROR? ──→ Runtime error feedback ──→ [SQL Generator] (retry)
     │
     │ Result rows
     ▼
[Insight Analyzer] ──→ Format + Narrative + Anomaly detection
     │
     ▼
Response (SQL + Data + Insight)
```

#### LAYER 3: KNOWLEDGE — Nền tảng tri thức

Đây là **layer quyết định accuracy**. Snowflake đạt 91% không nhờ LLM giỏi hơn mà nhờ semantic layer tốt hơn.

| Component | Vai trò | Dữ liệu chứa | Bắt buộc? |
|-----------|---------|---------------|-----------|
| **Semantic Layer** | Map business terms → SQL definitions | `"doanh thu" → SUM(sales.total_amount) WHERE status='completed'`, metric definitions, dimension mappings, sensitive columns list | **Bắt buộc** |
| **Vector Store** | Semantic search cho schema + queries | Schema embeddings (graph-aware chunks theo domain cluster), query embeddings | **Bắt buộc** |
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

**Vector Store — graph-aware chunking thay vì flat chunking:**

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

### Pattern 1: Sequential Multi-Agent Pipeline (Đề xuất chính)

```
                    ┌─────────────────────────────────────┐
                    │         ORCHESTRATOR                 │
                    │                                      │
  User Question ──→ │  Router → Linker → Generator        │
                    │            ↑           │             │
                    │            │      ┌────┴────┐        │
                    │            │      ▼         │        │
                    │         Validator ──FAIL──→ │        │
                    │            │         (retry) │        │
                    │         PASS                         │
                    │            │                          │
                    │         Executor → Insight ──→ Response
                    │                                      │
                    └─────────────────────────────────────┘
```

**Mô tả:** Mỗi agent đảm nhiệm 1 sub-problem chuyên biệt. Orchestrator điều phối tuần tự, có self-correction loop giữa Generator ↔ Validator.

| Ưu điểm | Nhược điểm |
|----------|------------|
| Separation of concerns rõ ràng — mỗi agent 1 nhiệm vụ | Latency cao hơn do sequential execution (~8-12s) |
| Dễ debug — biết lỗi ở agent nào | Nhiều components → phức tạp hơn để maintain |
| Self-correction tăng accuracy 15-20% | Cần orchestration logic (LangGraph hoặc custom) |
| Dễ thay thế/nâng cấp từng agent độc lập | Overhead cho queries đơn giản (L1) |
| Validate + audit ở mỗi bước → an toàn cho Banking | LLM cost cao hơn (nhiều API calls/query) |
| **Accuracy: 85-92%** | **Avg latency: 5-12s** |

**So sánh với phương pháp khác:**

| vs. | Sequential Pipeline tốt hơn ở | Sequential Pipeline kém hơn ở |
|-----|-------------------------------|-------------------------------|
| Single LLM call | Accuracy (+15-20%), safety, auditability | Latency, cost, simplicity |
| Parallel agents | Dễ debug, deterministic flow | Speed (parallel nhanh hơn ~30%) |
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
| Multi-Agent Pipeline | Speed, simplicity, cost | Accuracy, safety, debuggability |
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
         Single LLM  Multi-Agent  Multi-Agent
         No validate Full pipeline + Extended
         ~2-3s       ~5-8s         reasoning
                                   ~10-15s
```

**Mô tả:** Router phân loại query complexity, sau đó dispatch vào pipeline phù hợp. Query đơn giản đi "fast path" (1 LLM call), query phức tạp đi "deep path" (multi-agent + extended reasoning).

| Ưu điểm | Nhược điểm |
|----------|------------|
| Tối ưu latency: query đơn giản nhanh, phức tạp mới chậm | Router phải classify đúng — sai = sai cả pipeline |
| Tối ưu cost: không lãng phí multi-agent cho L1 queries | Phức tạp nhất trong 3 patterns |
| Best of both worlds — speed + accuracy | 3 paths = 3x testing/maintenance effort |
| Scalable — thêm tier mới khi cần | Router accuracy là single point of failure |
| Phù hợp cho production long-term | Cần nhiều data để train/tune Router |
| **Accuracy: 85-92%** | **Avg latency: 2-8s (adaptive)** |

**So sánh với phương pháp khác:**

| vs. | Adaptive Router tốt hơn ở | Adaptive Router kém hơn ở |
|-----|---------------------------|---------------------------|
| Fixed Multi-Agent | Speed cho simple queries, cost efficiency | Complexity, router accuracy risk |
| Single Agent | Accuracy cho complex queries | Simplicity |
| Fine-tuned + RAG | Flexibility, no GPU | Cold-start latency, dependency on LLM API |

---

### Tổng hợp so sánh 3 Patterns

| Tiêu chí | Pattern 1: Sequential Multi-Agent | Pattern 2: RAG Single Agent | Pattern 3: Adaptive Router |
|----------|----------------------------------|----------------------------|---------------------------|
| **Accuracy** | ⭐⭐⭐⭐⭐ 85-92% | ⭐⭐⭐ 75-85% | ⭐⭐⭐⭐⭐ 85-92% |
| **Latency** | ⭐⭐⭐ 5-12s | ⭐⭐⭐⭐⭐ 3-6s | ⭐⭐⭐⭐ 2-8s adaptive |
| **Complexity** | ⭐⭐⭐ Trung bình | ⭐⭐⭐⭐⭐ Thấp | ⭐⭐ Cao |
| **Safety** | ⭐⭐⭐⭐⭐ Validate riêng biệt | ⭐⭐ Self-validate | ⭐⭐⭐⭐ Validate cho L2+ |
| **Cost (LLM)** | ⭐⭐ Cao (nhiều calls) | ⭐⭐⭐⭐⭐ Thấp (1 call) | ⭐⭐⭐⭐ Tối ưu theo tier |
| **Maintainability** | ⭐⭐⭐⭐ Modular | ⭐⭐⭐⭐ Đơn giản | ⭐⭐ 3 paths |
| **Debuggability** | ⭐⭐⭐⭐⭐ Rõ từng step | ⭐⭐ Black-box | ⭐⭐⭐⭐ Rõ sau routing |
| **Phù hợp Banking** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐ |

### Khuyến nghị lộ trình

```
Phase 1 (R&D):     Bắt đầu với Pattern 2 (Single Agent) → validate feasibility nhanh
                    ↓
Phase 2 (POC):     Tiến hóa sang Pattern 1 (Multi-Agent) → đạt accuracy target 85%+
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

#### Pattern 1 — Sequential Multi-Agent (Phase 2)

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
| **LangGraph > custom code** | State management, conditional routing, streaming built-in | Learning curve, LangChain ecosystem dependency |
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

**Kết luận:** Pattern 1 (Sequential Multi-Agent) đạt điểm cao nhất nhờ accuracy và safety — hai yếu tố quan trọng nhất trong domain Banking. Tuy nhiên, lộ trình **Pattern 2 → 1 → 3** là con đường thực tế nhất vì cho phép validate nhanh rồi tiến hóa dần.

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

Schema Linker sử dụng **2 nguồn** để xây dựng relationship graph:

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
│          ┌──────────────┐                                   │
│          │ RELATIONSHIP │                                   │
│          │    GRAPH     │ → Adjacency list + JOIN conditions│
│          └──────────────┘                                   │
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
    → Build adjacency list (relationship graph)

  Bước 2: Query INFORMATION_SCHEMA (optional, validation)
    → Cross-validate FK constraints với schema.json
    → Log warnings nếu inconsistency

  Bước 3: Load semantic layer config
    → Overlay business aliases, domain clusters, sensitive columns
    → Merge user-defined relationships vào graph

  Bước 4: Generate embeddings
    → Graph-aware chunks (per domain cluster)
    → Upsert vào vector store

  Output: Relationship Graph + Embedded Chunks sẵn sàng

RUNTIME (mỗi query)
━━━━━━━━━━━━━━━━━━

  Input:  User question
  Step 1: Vector search → relevant domain cluster(s)
  Step 2: Graph traversal → extract tables + JOIN paths từ cluster
  Step 3: Resolve metrics + dimensions từ semantic layer
  Step 4: Fetch few-shot examples tương tự
  Output: Context Package → SQL Generator
```

---

## 8. MULTI-AGENT COMMUNICATION & HALLUCINATION

### 8.1 Vấn đề đặt ra

> Nếu tách Linker và Generator thành 2 agents, Generator có đủ thông tin về relationships không? Truyền qua nhiều agent có tăng hallucination không?

### 8.2 Generator nhận được gì từ Linker?

Linker **không chỉ trả về tên bảng**. Output của Linker là **Context Package** — một structured document chứa đầy đủ thông tin:

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

### 8.3 Multi-agent có tăng hallucination không?

**Không — nếu inter-agent contract là structured data. Thực tế nó giảm hallucination.**

#### So sánh trực tiếp:

| Yếu tố | Single Agent (1 LLM call) | Multi-Agent (Linker + Generator) |
|---------|--------------------------|----------------------------------|
| **Prompt size** | Rất dài — toàn bộ schema (14 bảng × 90 columns) + semantic rules + examples + output format | Ngắn và focused — Generator chỉ nhận 2-5 bảng liên quan |
| **Task complexity** | LLM phải đồng thời: tìm bảng + resolve metric + chọn JOIN + sinh SQL + validate | Mỗi agent chỉ 1 nhiệm vụ duy nhất |
| **Nguồn hallucination** | **Cao** — prompt dài + task phức tạp → LLM dễ "bịa" column/table không tồn tại | **Thấp** — Linker là retrieval (deterministic), search space của Generator bị thu hẹp |
| **Khi LLM bịa column** | Không ai kiểm tra → SQL fail ở runtime, user thấy lỗi | Validator agent bắt ngay → retry với error feedback |
| **Khi metric bị hiểu sai** | LLM tự diễn giải "doanh thu" → có thể sai | Semantic layer đã resolve sẵn → đúng definition |

#### Tại sao Linker KHÔNG gây hallucination?

```
Linker = Vector Search           → Deterministic (cosine similarity)
       + Metric Resolution       → Dictionary lookup (key → value)
       + JOIN Path Finder        → Graph traversal (BFS/DFS)
       + Few-shot Retrieval      → Similarity search (deterministic)

→ KHÔNG gọi LLM ở Linker → KHÔNG có cơ hội hallucinate
→ Output là structured data → Không có ambiguity khi truyền cho Generator
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

### 8.4 Inter-agent Contract — Nguyên tắc thiết kế

Để multi-agent KHÔNG tăng hallucination, tuân thủ 3 nguyên tắc:

| # | Nguyên tắc | Mô tả | Vi phạm → hậu quả |
|---|-----------|-------|---------------------|
| **1** | **Structured over Natural Language** | Inter-agent messages phải là JSON/typed objects, KHÔNG phải natural language | NL truyền giữa agents → mỗi agent diễn giải khác nhau → drift |
| **2** | **Complete Context Package** | Linker phải truyền ĐẦY ĐỦ: tables + JOINs + metrics + examples + enums | Thiếu JOIN path → Generator phải đoán → hallucinate |
| **3** | **Deterministic before Generative** | Linker (retrieval, lookup) chạy TRƯỚC Generator (LLM) | LLM phải vừa retrieve vừa generate → overload → hallucinate |

---

## 9. SEMANTIC LAYER — YÊU CẦU CHI TIẾT

### 9.1 Tổng quan

Semantic Layer là **nguồn tri thức nghiệp vụ** cho toàn bộ hệ thống. Nó bridge giữa ngôn ngữ business và cấu trúc database. Cần chứa **7 loại thông tin**:

```
┌─────────────────────────────────────────────────────────────────┐
│                      SEMANTIC LAYER                              │
│                                                                  │
│   ① Metric Definitions        ⑤ Sensitive Columns               │
│   ② Dimension Mappings        ⑥ Column Value Enums              │
│   ③ Table/Column Aliases      ⑦ Business Rules & Disambiguation │
│   ④ JOIN Graph                                                   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 9.2 Chi tiết từng loại thông tin

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

#### ④ JOIN Graph — Relationship Map

**Mục đích:** Cung cấp adjacency list đầy đủ để Linker biết cách nối bảng.

```json
{
  "join_graph": {
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

### 9.3 Semantic Layer — Tóm tắt

| # | Loại thông tin | Nguồn | Tần suất cập nhật |
|---|---------------|-------|-------------------|
| ① | Metric Definitions | Domain expert define | Khi thêm metric mới hoặc logic thay đổi |
| ② | Dimension Mappings | Domain expert define | Ít thay đổi (time patterns ổn định) |
| ③ | Table/Column Aliases | Domain expert define | Khi thêm bảng mới |
| ④ | JOIN Graph | Auto-detect + expert enrich | Khi schema thay đổi (migration) |
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

*Tài liệu Solution Suggestion v1.1 — Cập nhật phân tích Scale-up, Linker Relationships, Multi-Agent Hallucination, Semantic Layer Requirements*
*Ngày tạo: 25/03/2026 | Cập nhật: 25/03/2026*
*Phần tiếp theo: [Architecture Design](./architecture_design.md) — Chi tiết thiết kế từng component*
