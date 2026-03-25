# SOLUTION ARCHITECTURE: Text-to-SQL Agent Platform
### Phân tích Vấn đề & Thiết kế Giải pháp | Solution Architect Report

---

## PHẦN I: PHÂN TÍCH VẤN ĐỀ (PROBLEM ANALYSIS)

---

### 1. BÀI TOÁN CỐT LÕI

Bài toán được đặt ra: **Cho phép người dùng không biết SQL đặt câu hỏi bằng ngôn ngữ tự nhiên và nhận được câu trả lời chính xác từ database.**

Nghe đơn giản, nhưng phân rã ra có **6 sub-problems** mà hệ thống phải giải quyết đồng thời:

```
                        "Top 10 merchant có doanh thu cao nhất quý trước?"
                                          │
                    ┌─────────────────────┼──────────────────────┐
                    │                     │                      │
             P1: HIỂU Ý ĐỊNH      P2: TÌM DỮ LIỆU      P3: SINH SQL
             Người dùng muốn gì?  Dữ liệu nằm ở đâu?   SQL nào đúng?
                    │                     │                      │
                    └─────────────────────┼──────────────────────┘
                                          │
                    ┌─────────────────────┼──────────────────────┐
                    │                     │                      │
             P4: KIỂM TRA          P5: THỰC THI           P6: GIẢI THÍCH
             SQL có an toàn?       Chạy và xử lý lỗi?    Trình bày kết quả?
                    │                     │                      │
                    └─────────────────────┴──────────────────────┘
```

---

### 2. PHÂN TÍCH TỪ CODEBASE HIỆN TẠI

#### 2.1 Những gì đã có (Assets)

| Asset | File | Đánh giá |
|-------|------|----------|
| **Database Schema** | `data/schema.json` | 14 bảng, 90+ columns, có description + type + constraints + relationships. **Chất lượng tốt.** |
| **Business Queries** | `data/query.json` | 20 câu hỏi + SQL + explanation. **Golden dataset tốt cho evaluation.** |
| **Complex Queries** | `data/query_samples.sql` | 20 queries phức tạp (CTE, window, HAVING, subquery). **Training data tốt.** |
| **Data Generator** | `gen_data.py` | 200K+ records, seeded, batch insert. **Production-grade data gen.** |
| **RAG Chunking** | `rag/simple/chunking.py` | ChromaDB + bge-large-en-v1.5. **Prototype, cần nâng cấp đáng kể.** |
| **Infrastructure** | `docker/docker-compose.yml` | PostgreSQL 18 + pgvector. **Tốt, đã sẵn sàng.** |
| **Retrieval** | `rag/simple/retrive.py` | **Empty - chưa implement.** |

#### 2.2 Phân tích Gap - 6 Sub-problems

---

**P1: INTENT UNDERSTANDING (Hiểu ý định)**

```
Vấn đề: Câu hỏi ngôn ngữ tự nhiên có nhiều cách diễn đạt cho cùng một ý.
```

| Ví dụ câu hỏi | Thách thức |
|----------------|-----------|
| "Doanh thu tháng trước" | "Doanh thu" = SUM(total_amount)? hay COUNT(*)? "Tháng trước" = calendar month? hay 30 ngày? |
| "Khách hàng nào inactive?" | "Inactive" = không có sales? hay không có transfers? Bao lâu thì coi là inactive? |
| "So sánh VISA vs Mastercard" | So sánh cái gì? Số lượng giao dịch? Tổng giá trị? Tỷ lệ refund? |

**Gap hiện tại:** Chưa có layer nào xử lý ambiguity. Hệ thống chưa có khả năng hỏi lại (clarification). Chưa có business glossary mapping "doanh thu" → `SUM(sales.total_amount) WHERE status = 'completed'`.

---

**P2: SCHEMA LINKING (Tìm đúng bảng/cột)**

```
Vấn đề: Database có 14 bảng, 90+ columns. LLM cần biết chính xác
         bảng nào liên quan, JOIN như thế nào, column nào map với concept nào.
```

| Câu hỏi | Bảng cần | JOIN path | Độ phức tạp |
|----------|----------|-----------|-------------|
| "KYC status distribution" | customers | Không JOIN | Thấp |
| "Top products by revenue" | sales → products | 1 JOIN | Trung bình |
| "Refund rate per merchant" | merchants → sales → refunds | 2 JOINs | Cao |
| "Self-transfer detection" | transfers → accounts (x2) → customers | 3 JOINs | Rất cao |
| "Card network usage in sales" | sales → cards | 1 JOIN (cross-table FK) | Trung bình |

**Gap hiện tại:**
- `chunking.py` flatten toàn bộ schema thành text → mất cấu trúc relationship.
- Mỗi bảng được embed độc lập → không capture được JOIN paths.
- Embedding model (bge-large-en-v1.5) chỉ hiểu English → Vietnamese queries sẽ fail.

**Ví dụ cụ thể về lỗi chunking hiện tại:**

```python
# Hiện tại: flatten_json_to_text() tạo ra text như này:
"name: sales\ndescription: Records of sales transactions at terminals.\ncolumns: [...]"

# Vấn đề: Relationships bị mất!
# LLM không biết sales.card_id → cards.id → cards.network
# Khi hỏi "VISA vs Mastercard", LLM có thể không tìm được path
```

---

**P3: SQL GENERATION (Sinh SQL chính xác)**

```
Vấn đề: Sinh SQL đúng syntax, đúng logic, đúng semantic cho PostgreSQL.
```

Phân tích 40 queries hiện có (query.json + query_samples.sql) theo complexity:

| Level | Số lượng | SQL Features | Ví dụ |
|-------|---------|-------------|-------|
| **L1: Simple** | 8 | SELECT, WHERE, GROUP BY, COUNT/SUM/AVG | KYC distribution, balance by type |
| **L2: Join** | 12 | INNER/LEFT JOIN, multi-table | Top products, card network usage |
| **L3: Advanced** | 10 | CTE, Window functions, HAVING, subqueries | Running cumulative, percentile, relational division |
| **L4: Complex** | 10 | Self-join, INTERSECT, anti-join, correlated subquery | Self-transfer, mutual transfers, JSONB query |

**Gap hiện tại:** Chưa có LLM integration. Chưa có mechanism để:
- Cung cấp schema context cho LLM
- Cung cấp similar examples (few-shot)
- Chỉ định PostgreSQL dialect (không phải MySQL, T-SQL)

---

**P4: QUERY VALIDATION (Kiểm tra SQL)**

```
Vấn đề: LLM có thể sinh SQL sai syntax, sai logic, hoặc nguy hiểm.
```

| Rủi ro | Ví dụ | Hậu quả |
|--------|-------|---------|
| **SQL Injection** | LLM bị prompt injection → `DROP TABLE` | Mất dữ liệu |
| **Performance** | `SELECT * FROM sales` (200K rows, no LIMIT) | DB overload |
| **Wrong logic** | `INNER JOIN` thay vì `LEFT JOIN` → mất records | Kết quả sai |
| **Hallucination** | Dùng column/table không tồn tại | Runtime error |
| **Sensitive data** | Query CVV, card numbers | Data breach |

**Gap hiện tại:** Không có validation layer nào. Database connection không phải read-only.

---

**P5: QUERY EXECUTION (Thực thi SQL)**

```
Vấn đề: Chạy SQL trên production DB an toàn, xử lý lỗi, timeout.
```

**Gap hiện tại:**
- `gen_data.py` connect với `autocommit = True` → nguy hiểm cho production.
- Không có connection pooling.
- Không có query timeout.
- Không có error handling/retry logic.

---

**P6: RESULT PRESENTATION (Trình bày kết quả)**

```
Vấn đề: Raw SQL result → insight dễ hiểu cho business user.
```

**Gap hiện tại:** Chưa có layer nào xử lý output. Cần:
- Format bảng kết quả.
- Sinh narrative giải thích.
- Phát hiện anomalies.

---

### 3. ROOT CAUSE ANALYSIS

Tổng hợp các gap theo mức độ ưu tiên:

```
    ┌────────────────────────────────────────────────────────┐
    │                    CRITICAL GAP                         │
    │  Không có "não": LLM Agent + Retrieval + Execution     │
    │  → Hệ thống hiện tại chỉ có data, chưa có intelligence │
    └──────────────────────┬─────────────────────────────────┘
                           │
         ┌─────────────────┼─────────────────┐
         │                 │                 │
    ┌────┴────┐      ┌─────┴─────┐     ┌────┴────┐
    │ Schema  │      │    LLM    │     │ Query   │
    │ Linking │      │ Orchestr. │     │ Safety  │
    │ quá thô │      │ chưa có   │     │ chưa có │
    └─────────┘      └───────────┘     └─────────┘
         │                 │                 │
    Chunking flat    Chưa có agent    Chưa có validation
    Mất relationship Chưa có prompt   Chưa có read-only
    Chưa có glossary Chưa có retry    Chưa có timeout
```

---

## PHẦN II: THIẾT KẾ GIẢI PHÁP (SOLUTION DESIGN)

---

### 4. KIẾN TRÚC TỔNG THỂ (High-Level Architecture)

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         PRESENTATION LAYER                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐                              │
│  │ Chat UI  │  │   API    │  │   CLI    │                              │
│  │ (Web)    │  │ (REST)   │  │ (Dev)    │                              │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘                              │
│       └──────────────┴─────────────┘                                    │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────────────────┐
│                      AGENT ORCHESTRATION LAYER                           │
│                                                                          │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                      ROUTER AGENT                                │    │
│  │  Phân loại intent → dispatch sang agent phù hợp                 │    │
│  └──────┬──────────────────┬──────────────────┬────────────────────┘    │
│         │                  │                  │                         │
│  ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐                 │
│  │   SCHEMA    │    │    SQL      │    │  INSIGHT    │                 │
│  │   LINKER    │    │  GENERATOR  │    │  ANALYZER   │                 │
│  │   AGENT     │    │  AGENT      │    │  AGENT      │                 │
│  │             │    │             │    │             │                 │
│  │ • Xác định  │    │ • Sinh SQL  │    │ • Phân tích │                 │
│  │   tables    │    │ • Few-shot  │    │   kết quả   │                 │
│  │ • Map JOIN  │    │ • Self-     │    │ • Anomaly   │                 │
│  │   paths     │    │   correct   │    │   detection │                 │
│  └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                 │
│         │                  │                  │                         │
│  ┌──────┴──────────────────┴──────────────────┴──────┐                 │
│  │              VALIDATOR AGENT                       │                 │
│  │  • SQL syntax check    • Sensitive column filter  │                 │
│  │  • Execution dry-run   • Performance guard        │                 │
│  └───────────────────────────────────────────────────┘                 │
│                                                                          │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────────────────┐
│                        KNOWLEDGE LAYER                                   │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │   SEMANTIC   │  │   VECTOR     │  │   EXAMPLE    │                  │
│  │   LAYER      │  │   STORE      │  │   STORE      │                  │
│  │              │  │              │  │              │                  │
│  │ • Business   │  │ • Schema     │  │ • Golden     │                  │
│  │   glossary   │  │   embeddings │  │   queries    │                  │
│  │ • Metric     │  │ • Query      │  │ • User       │                  │
│  │   definitions│  │   embeddings │  │   corrections│                  │
│  │ • JOIN graph │  │ • ChromaDB   │  │ • Few-shot   │                  │
│  └──────────────┘  └──────────────┘  └──────────────┘                  │
│                                                                          │
└──────────────────────┬──────────────────────────────────────────────────┘
                       │
┌──────────────────────┴──────────────────────────────────────────────────┐
│                        DATA ACCESS LAYER                                 │
│                                                                          │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                  │
│  │  CONNECTION  │  │   QUERY      │  │   AUDIT      │                  │
│  │  POOL        │  │   EXECUTOR   │  │   LOGGER     │                  │
│  │              │  │              │  │              │                  │
│  │ • Read-only  │  │ • Timeout    │  │ • Who asked  │                  │
│  │ • Pooled     │  │ • Row limit  │  │ • What SQL   │                  │
│  │ • Isolated   │  │ • Retry      │  │ • What result│                  │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘                  │
│         └─────────────────┴─────────────────┘                           │
│                           │                                              │
│                  ┌────────┴────────┐                                     │
│                  │   PostgreSQL    │                                     │
│                  │   + pgvector    │                                     │
│                  │   (Read Replica)│                                     │
│                  └─────────────────┘                                     │
│                                                                          │
└──────────────────────────────────────────────────────────────────────────┘
```

---

### 5. CHI TIẾT TỪNG LAYER

---

#### 5.1 KNOWLEDGE LAYER - Nền tảng Tri thức

**Đây là layer quan trọng nhất.** Snowflake đạt 90-95% accuracy không nhờ LLM giỏi hơn, mà nhờ semantic layer tốt hơn.

##### 5.1.1 Semantic Layer (Business Glossary + Metric Definitions)

**Vấn đề giải quyết:** "Doanh thu" nghĩa là gì chính xác trong hệ thống?

```json
// semantic_layer.json - PHẢI XÂY DỰNG
{
  "metrics": {
    "doanh_thu": {
      "aliases": ["revenue", "doanh thu", "doanh số", "total sales"],
      "definition": "SUM(sales.total_amount) WHERE sales.status = 'completed'",
      "tables": ["sales"],
      "filters": {"sales.status": "completed"},
      "note": "Chỉ tính giao dịch completed, không tính pending/failed"
    },
    "ti_le_hoan_tien": {
      "aliases": ["refund rate", "tỷ lệ hoàn tiền", "tỷ lệ refund"],
      "definition": "COUNT(refunds.id)::decimal / COUNT(sales.id)",
      "tables": ["sales", "refunds"],
      "join": "LEFT JOIN refunds ON refunds.sale_id = sales.id",
      "note": "LEFT JOIN vì không phải sale nào cũng có refund"
    },
    "khach_hang_moi": {
      "aliases": ["new customers", "khách hàng mới", "onboarded"],
      "definition": "COUNT(*) FROM customers WHERE created_at IN period",
      "tables": ["customers"]
    },
    "so_du_tai_khoan": {
      "aliases": ["account balance", "số dư", "balance"],
      "definition": "accounts.balance",
      "tables": ["accounts"],
      "note": "balance là snapshot, không phải tổng transactions"
    }
  },
  "dimensions": {
    "thoi_gian": {
      "aliases": ["tháng trước", "quý trước", "last month", "last quarter"],
      "mapping": {
        "tháng trước": "DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')",
        "quý trước": "DATE_TRUNC('quarter', CURRENT_DATE - INTERVAL '1 quarter')",
        "năm nay": "DATE_TRUNC('year', CURRENT_DATE)"
      }
    }
  },
  "sensitive_columns": [
    "cards.cvv",
    "cards.card_number",
    "customers.dob",
    "customers.email",
    "customers.phone"
  ]
}
```

##### 5.1.2 Schema Graph (JOIN Path Map)

**Vấn đề giải quyết:** Chunking hiện tại mất relationships. LLM không biết JOIN path.

```
                    branches
                       │ 1:N
                    employees

    customers ──1:N── accounts ──1:N── cards
                  │         │              │
                  │         │              │
                  │    1:N  │  1:N         │
                  │  statements  transfers │
                  │                        │
                  └────────────────────────┘
                              │
                           sales ──N:1── merchants ──1:N── terminals
                              │
                           products
                              │
                           refunds

                        audit_logs (standalone)
```

**Thiết kế:** Thay vì flatten từng bảng độc lập, tạo **graph-aware chunks**:

```python
# Thay vì: mỗi bảng = 1 chunk (hiện tại)
# Đổi thành: mỗi "domain cluster" = 1 chunk

DOMAIN_CLUSTERS = {
    "customer_profile": {
        "tables": ["customers", "accounts", "cards"],
        "join_paths": [
            "customers.id = accounts.customer_id",
            "accounts.id = cards.account_id"
        ],
        "use_cases": ["KYC", "balance inquiry", "card management"]
    },
    "transaction_analytics": {
        "tables": ["sales", "merchants", "terminals", "products", "cards"],
        "join_paths": [
            "sales.merchant_id = merchants.id",
            "sales.terminal_id = terminals.id",
            "sales.product_id = products.id",
            "sales.card_id = cards.id"
        ],
        "use_cases": ["revenue analysis", "product performance", "merchant analytics"]
    },
    "refund_analysis": {
        "tables": ["refunds", "sales", "merchants"],
        "join_paths": [
            "refunds.sale_id = sales.id",
            "sales.merchant_id = merchants.id"
        ],
        "use_cases": ["refund rate", "refund reasons", "merchant quality"]
    },
    "transfer_analytics": {
        "tables": ["transfers", "accounts", "customers"],
        "join_paths": [
            "transfers.from_account = accounts.id",
            "transfers.to_account = accounts.id",
            "accounts.customer_id = customers.id"
        ],
        "use_cases": ["self-transfer detection", "transfer volume", "fraud detection"]
    },
    "hr_branch": {
        "tables": ["branches", "employees"],
        "join_paths": ["employees.branch_id = branches.id"],
        "use_cases": ["employee count", "branch performance", "hiring trends"]
    },
    "audit_compliance": {
        "tables": ["audit_logs"],
        "join_paths": [],
        "use_cases": ["action frequency", "fraud investigation", "compliance"]
    },
    "account_statements": {
        "tables": ["statements", "accounts"],
        "join_paths": ["statements.account_id = accounts.id"],
        "use_cases": ["balance changes", "account activity"]
    }
}
```

##### 5.1.3 Example Store (Few-shot Learning)

**Vấn đề giải quyết:** LLM accuracy tăng đáng kể khi có similar examples.

```
Hiện có:
├── query.json        → 20 business Q&A pairs (Golden set)
├── query_samples.sql → 20 complex queries (Advanced patterns)
└── Tổng: 40 examples

Cần mở rộng thành:
├── golden_queries/     → 40 verified Q&A (từ query.json + query_samples.sql)
├── user_corrections/   → Queries mà user sửa → feedback loop
└── pattern_templates/  → SQL patterns cho CTE, window, subquery, etc.
```

---

#### 5.2 AGENT ORCHESTRATION LAYER - Bộ não

##### 5.2.1 Luồng xử lý chính (Main Pipeline)

```
                         User Question
                              │
                    ┌─────────┴─────────┐
                    │   ROUTER AGENT    │
                    │                   │
                    │ 1. Classify type: │
                    │    • SQL query    │
                    │    • Clarification│
                    │    • Chitchat     │
                    │    • Out-of-scope │
                    └────────┬──────────┘
                             │
              ┌──────────────┼──────────────┐
              │ SQL query    │ Clarify      │ Out-of-scope
              ↓              ↓              ↓
    ┌─────────────────┐  Ask user for   "Xin lỗi, tôi chỉ
    │  SCHEMA LINKER  │  more detail    hỗ trợ truy vấn dữ liệu"
    │                 │
    │ 1. Retrieve     │
    │    relevant     │
    │    domain       │
    │    clusters     │
    │ 2. Resolve      │
    │    metric       │
    │    definitions  │
    │ 3. Build        │
    │    context      │
    │    (tables +    │
    │     JOINs +     │
    │     examples)   │
    └────────┬────────┘
             │ Context Package
             ↓
    ┌─────────────────┐
    │  SQL GENERATOR  │
    │                 │
    │ 1. Build prompt │
    │    with:        │
    │    • Schema ctx │
    │    • Metrics    │
    │    • Few-shot   │
    │    • Dialect    │
    │ 2. Call LLM     │
    │ 3. Parse SQL    │
    └────────┬────────┘
             │ Generated SQL
             ↓
    ┌─────────────────┐
    │   VALIDATOR     │
    │                 │──── FAIL ──→ Feedback to Generator
    │ 1. Syntax check │              (retry max 3 lần)
    │ 2. Table/column │
    │    exists?      │
    │ 3. Sensitive     │
    │    column?      │
    │ 4. Has LIMIT?   │
    │ 5. Is SELECT?   │
    │    (no DML)     │
    │ 6. EXPLAIN cost │
    └────────┬────────┘
             │ Validated SQL
             ↓
    ┌─────────────────┐
    │   EXECUTOR      │
    │                 │
    │ 1. Execute with │
    │    timeout      │
    │ 2. Fetch rows   │
    │ 3. Handle error │──── ERROR ──→ Feedback to Generator
    └────────┬────────┘              (retry with error message)
             │ Result rows
             ↓
    ┌─────────────────┐
    │ INSIGHT ANALYZER│
    │                 │
    │ 1. Format table │
    │ 2. Generate     │
    │    narrative    │
    │ 3. Detect       │
    │    anomalies   │
    │ 4. Suggest      │
    │    follow-up   │
    └────────┬────────┘
             │
             ↓
         Response to User
         (SQL + Result + Insight)
```

##### 5.2.2 Self-Correction Loop (Điểm khác biệt quan trọng)

```
Tại sao cần self-correction?
─────────────────────────────
LLM sinh SQL sai ~15-40% trường hợp (tùy complexity).
Nhưng khi được cung cấp error message, khả năng tự sửa lên đến 60-80%.

Luồng:
                    ┌──────────────────────┐
                    │    SQL Generator     │
                    └──────────┬───────────┘
                               │ SQL v1
                               ↓
                    ┌──────────────────────┐
                    │     Validator        │──→ Syntax error?
                    └──────────┬───────────┘    Column not found?
                               │                     │
                        PASS   │              FAIL   │
                               │                     │
                               ↓                     ↓
                    ┌──────────────────────┐  ┌──────────────────┐
                    │     Executor         │  │  Error Feedback  │
                    └──────────┬───────────┘  │                  │
                               │              │ "Column 'revenue'│
                        OK     │              │  does not exist. │
                               │              │  Did you mean    │
                               ↓              │  'total_amount'?"│
                          Return Result       └────────┬─────────┘
                                                       │
                                                       ↓
                                              SQL Generator (retry)
                                              with error context
                                                       │
                                              Max 3 retries, then
                                              return error to user
```

---

#### 5.3 DATA ACCESS LAYER - Lớp An toàn

##### 5.3.1 Connection Strategy

```python
# THIẾT KẾ: Dual connection model
#
# Connection 1: READ-ONLY (cho query execution)
#   - PostgreSQL read replica hoặc read-only transaction
#   - statement_timeout = 30s
#   - row_limit = 1000
#   - connection pooling (min=2, max=10)
#
# Connection 2: ADMIN (cho data gen, schema migration)
#   - Chỉ dùng trong development
#   - Không expose cho agent pipeline

CONNECTION_CONFIG = {
    "query_executor": {
        "host": "DB_HOST",
        "port": 5432,
        "dbname": "test_db",
        "user": "readonly_user",          # Tạo user riêng!
        "options": "-c statement_timeout=30000",  # 30s timeout
        "default_transaction_isolation": "read only"
    }
}
```

##### 5.3.2 Query Safety Rules

```
ALLOWED:
  ✓ SELECT statements
  ✓ WITH (CTE) ... SELECT
  ✓ EXPLAIN SELECT (cho cost estimation)

BLOCKED:
  ✗ INSERT, UPDATE, DELETE, DROP, ALTER, TRUNCATE
  ✗ CREATE, GRANT, REVOKE
  ✗ COPY, pg_read_file, pg_ls_dir
  ✗ DO $$ ... $$ (arbitrary code execution)
  ✗ SELECT without LIMIT (auto-add LIMIT 1000)
  ✗ SELECT on sensitive columns (cvv, card_number)

GUARDED:
  ⚠ Queries with estimated cost > threshold → require confirmation
  ⚠ Cross-join detection → warn user
  ⚠ Full table scan on sales (200K rows) → suggest filter
```

---

### 6. TECHNOLOGY STACK DECISIONS

| Layer | Component | Lựa chọn | Lý do |
|-------|-----------|----------|-------|
| **LLM** | Primary | Claude API (claude-sonnet-4-6) | Tool use tốt, accuracy cao, cost hợp lý |
| **LLM** | Fallback / Complex | Claude claude-opus-4-6 | Cho complex queries cần reasoning sâu |
| **Vector DB** | Embeddings | ChromaDB (dev) → PostgreSQL pgvector (prod) | Đã có cả hai; consolidate vào 1 DB ở prod |
| **Embedding** | Model | bge-large-en-v1.5 (hiện tại) | Giữ nguyên cho English; thêm multilingual sau |
| **Framework** | Agent orchestration | LangGraph hoặc Custom Python | LangGraph cho graph-based agent routing |
| **API** | Web framework | FastAPI | Async, OpenAPI docs, WebSocket cho streaming |
| **UI** | Frontend | Streamlit (POC) → React (Production) | Streamlit nhanh cho demo; React cho UX tốt |
| **Database** | Primary | PostgreSQL 18 + pgvector | Đã setup, production-grade |
| **Cache** | Query cache | Redis | Cache kết quả cho queries lặp lại |
| **Monitoring** | Observability | Prometheus + Grafana | Standard stack |

---

### 7. PROJECT STRUCTURE (Target)

```
Text2SQL/
├── data/
│   ├── schema.json                 # ✅ Đã có
│   ├── query.json                  # ✅ Đã có
│   ├── query_samples.sql           # ✅ Đã có
│   └── semantic_layer.json         # 🆕 Business glossary + metrics
│
├── src/
│   ├── agents/
│   │   ├── router.py               # 🆕 Intent classification
│   │   ├── schema_linker.py        # 🆕 Schema retrieval + JOIN path
│   │   ├── sql_generator.py        # 🆕 LLM prompt + SQL generation
│   │   ├── validator.py            # 🆕 SQL safety + syntax check
│   │   ├── executor.py             # 🆕 Safe query execution
│   │   └── insight_analyzer.py     # 🆕 Result → narrative
│   │
│   ├── knowledge/
│   │   ├── semantic_layer.py       # 🆕 Load & resolve metrics
│   │   ├── schema_graph.py         # 🆕 Domain clusters + JOIN paths
│   │   ├── embeddings.py           # 🔄 Refactor từ chunking.py
│   │   └── example_store.py        # 🆕 Few-shot example retrieval
│   │
│   ├── data_access/
│   │   ├── connection_pool.py      # 🆕 Read-only pooled connections
│   │   ├── query_runner.py         # 🆕 Safe execution + timeout
│   │   └── audit_logger.py         # 🆕 Log all queries + results
│   │
│   ├── api/
│   │   ├── main.py                 # 🆕 FastAPI application
│   │   ├── routes.py               # 🆕 REST + WebSocket endpoints
│   │   └── models.py               # 🆕 Request/Response schemas
│   │
│   └── config.py                   # 🆕 Centralized configuration
│
├── tests/
│   ├── test_schema_linker.py       # 🆕 Schema linking accuracy
│   ├── test_sql_generator.py       # 🆕 SQL generation vs golden set
│   ├── test_validator.py           # 🆕 Safety rules
│   ├── test_executor.py            # 🆕 Execution edge cases
│   └── eval/
│       └── accuracy_eval.py        # 🆕 End-to-end accuracy measurement
│
├── docker/
│   ├── docker-compose.yml          # ✅ Đã có (PostgreSQL + pgvector)
│   └── docker-compose.full.yml     # 🆕 Full stack (DB + API + UI)
│
├── rag/simple/                     # ✅ Giữ lại làm reference
│   ├── chunking.py
│   └── retrive.py
│
├── gen_data.py                     # ✅ Đã có
├── requirements.txt                # 🆕
├── .env                            # ✅ Đã có
└── docs/                           # ✅ Đã có (từ task trước)
```

---

### 8. LLM PROMPT ARCHITECTURE

Prompt là "linh hồn" của hệ thống. Thiết kế prompt theo cấu trúc 5 phần:

```
┌──────────────────────────────────────────────────────────┐
│ SYSTEM PROMPT                                             │
│                                                           │
│ ① ROLE & CONSTRAINTS                                     │
│   "You are a SQL expert for a banking/POS PostgreSQL     │
│    database. Generate ONLY SELECT queries. Never access   │
│    columns: cvv, card_number."                           │
│                                                           │
│ ② SCHEMA CONTEXT (from Schema Linker)                    │
│   "Relevant tables for this query:                       │
│    TABLE sales (id UUID PK, sale_time TIMESTAMP,         │
│    merchant_id UUID FK→merchants.id, ...)"               │
│                                                           │
│ ③ SEMANTIC RULES (from Semantic Layer)                   │
│   "Business rules:                                       │
│    - 'revenue' = SUM(sales.total_amount)                 │
│      WHERE status='completed'                            │
│    - 'last month' = DATE_TRUNC('month',                  │
│      CURRENT_DATE - INTERVAL '1 month')"                 │
│                                                           │
│ ④ FEW-SHOT EXAMPLES (from Example Store)                 │
│   "Example 1:                                            │
│    Q: What is the refund rate per merchant?               │
│    SQL: SELECT m.name, COUNT(r.id)::decimal /            │
│         COUNT(s.id) AS refund_rate ..."                   │
│                                                           │
│ ⑤ OUTPUT FORMAT                                          │
│   "Return JSON: {sql: ..., explanation: ...,             │
│    tables_used: [...], confidence: 0-1}"                 │
│                                                           │
├──────────────────────────────────────────────────────────┤
│ USER MESSAGE                                              │
│   "Top 10 merchants có doanh thu cao nhất quý trước?"    │
└──────────────────────────────────────────────────────────┘
```

---

### 9. EVALUATION FRAMEWORK

**Đo lường accuracy bằng golden dataset hiện có:**

```
Evaluation Pipeline:

  query.json (20 Q&A)  ─→  Run agent  ─→  Compare output SQL
  query_samples.sql    ─→  với golden     vs golden SQL
  (20 patterns)            queries        (execution match)

Metrics:
┌────────────────────────────────────────────────┐
│ Metric              │ Target  │ Method         │
│─────────────────────┼─────────┼────────────────│
│ Execution Accuracy  │ ≥ 85%   │ Cùng result?   │
│ Exact Match         │ ≥ 60%   │ Cùng SQL?      │
│ Valid SQL Rate      │ ≥ 95%   │ Chạy được?     │
│ Safety Pass Rate    │ 100%    │ Không DML?     │
│ Avg Latency         │ ≤ 8s    │ End-to-end     │
│ Schema Link Recall  │ ≥ 90%   │ Đúng tables?   │
│ Self-Correct Rate   │ Track   │ Bao nhiêu %    │
│                     │         │ sửa thành công? │
└────────────────────────────────────────────────┘
```

---

### 10. SEQUENCE DIAGRAM - LUỒNG END-TO-END

```
User          Router       SchemaLinker    SQLGenerator    Validator      Executor       Insight
  │              │              │              │              │              │              │
  │─"Top 10     │              │              │              │              │              │
  │  merchant"─→│              │              │              │              │              │
  │              │              │              │              │              │              │
  │              │─classify()─→│              │              │              │              │
  │              │ type="sql"   │              │              │              │              │
  │              │              │              │              │              │              │
  │              │──link()─────→│              │              │              │              │
  │              │              │─query        │              │              │              │
  │              │              │ ChromaDB     │              │              │              │
  │              │              │─resolve      │              │              │              │
  │              │              │ metrics      │              │              │              │
  │              │              │─find JOIN    │              │              │              │
  │              │              │ paths        │              │              │              │
  │              │              │              │              │              │              │
  │              │              │←─context─────│              │              │              │
  │              │              │  package     │              │              │              │
  │              │              │              │              │              │              │
  │              │──generate()─────────────────→│              │              │              │
  │              │              │              │─build prompt │              │              │
  │              │              │              │─call LLM     │              │              │
  │              │              │              │─parse SQL    │              │              │
  │              │              │              │              │              │              │
  │              │              │              │←─SQL─────────│              │              │
  │              │              │              │              │              │              │
  │              │──validate()────────────────────────────────→│              │              │
  │              │              │              │              │─syntax OK?   │              │
  │              │              │              │              │─tables exist?│              │
  │              │              │              │              │─safe?        │              │
  │              │              │              │              │─EXPLAIN cost │              │
  │              │              │              │              │              │              │
  │              │              │              │              │←─PASS────────│              │
  │              │              │              │              │              │              │
  │              │──execute()──────────────────────────────────────────────→│              │
  │              │              │              │              │              │─run SQL      │
  │              │              │              │              │              │ (read-only)  │
  │              │              │              │              │              │─fetch rows   │
  │              │              │              │              │              │              │
  │              │              │              │              │              │←─rows────────│
  │              │              │              │              │              │              │
  │              │──analyze()───────────────────────────────────────────────────────────→│
  │              │              │              │              │              │              │─format
  │              │              │              │              │              │              │─narrative
  │              │              │              │              │              │              │─anomalies
  │              │              │              │              │              │              │
  │←─response───│              │              │              │              │              │
  │  (SQL +      │              │              │              │              │              │
  │   result +   │              │              │              │              │              │
  │   insight)   │              │              │              │              │              │
  │              │              │              │              │              │              │
```

---

### 11. DEPLOYMENT ARCHITECTURE

```
┌─────────────────── Docker Compose Stack ────────────────────┐
│                                                              │
│  ┌────────────┐  ┌────────────┐  ┌────────────┐            │
│  │  Nginx     │  │  FastAPI   │  │  Streamlit  │            │
│  │  (reverse  │→│  (Agent    │  │  (Chat UI)  │            │
│  │   proxy)   │  │   API)     │  │  Port 8501  │            │
│  │  Port 80   │  │  Port 8000 │  │             │            │
│  └────────────┘  └─────┬──────┘  └─────────────┘            │
│                        │                                     │
│         ┌──────────────┼──────────────┐                     │
│         │              │              │                     │
│  ┌──────┴─────┐  ┌─────┴─────┐  ┌────┴──────┐             │
│  │ PostgreSQL │  │  Redis    │  │ ChromaDB  │             │
│  │ + pgvector │  │  (cache)  │  │ (vectors) │             │
│  │ Port 5432  │  │ Port 6379 │  │ Port 8100 │             │
│  └────────────┘  └───────────┘  └───────────┘             │
│                                                              │
│  External:                                                   │
│  └── Claude API (Anthropic) ← outbound HTTPS only          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

### 12. TỔNG KẾT QUYẾT ĐỊNH KIẾN TRÚC

| # | Quyết định | Lý do | Trade-off |
|---|-----------|-------|-----------|
| **AD-1** | Agentic pipeline (multi-agent) thay vì single-shot | Self-correction tăng accuracy 15-20% | Latency tăng ~2-3s, phức tạp hơn |
| **AD-2** | Semantic layer + domain clusters thay vì flat chunking | Key to 85%+ accuracy (bài học Snowflake) | Cần maintain business glossary thủ công |
| **AD-3** | Claude API thay vì self-hosted LLM | Accuracy cao hơn SQLCoder, không cần GPU | Phụ thuộc external API, có latency |
| **AD-4** | PostgreSQL pgvector thay vì ChromaDB riêng (prod) | Giảm infra complexity, 1 DB cho tất cả | pgvector performance kém hơn dedicated vector DB ở scale lớn |
| **AD-5** | Read-only connection + SQL allowlist | Bắt buộc cho security | Không thể chạy stored procedures |
| **AD-6** | Retry with error feedback (max 3) | 60-80% self-correct rate | Tăng latency + API cost khi retry |
| **AD-7** | Streamlit → React cho UI | Nhanh cho POC, đầu tư UI sau | Phải rewrite frontend ở Phase 3 |

---

*Tài liệu Solution Architecture v1.0*
*Ngày tạo: 25/03/2026*
