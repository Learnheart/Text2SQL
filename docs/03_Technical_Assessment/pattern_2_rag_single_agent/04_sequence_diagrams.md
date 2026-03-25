# Sequence Diagrams — RAG-Enhanced Single Agent

## Diagram 1: E2E Happy Path

Luồng đơn giản nhất — user hỏi, agent sinh SQL, execute, trả kết quả. So với Pattern 1, ít actors hơn (không có Router, Validator, Executor riêng).

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant RAG as RAG Retrieval Module
    participant VS as Vector Store (ChromaDB)
    participant PB as Prompt Builder
    participant Claude as Claude Sonnet (Agent)
    participant PG as PostgreSQL

    User->>API: POST /api/query<br/>"Top 10 merchant doanh thu cao nhất quý trước?"

    API->>RAG: retrieve_context(question)
    RAG->>VS: vector search (schema chunks, top_k=5)
    VS-->>RAG: schema chunks liên quan
    RAG->>VS: vector search (examples, top_k=3)
    VS-->>RAG: few-shot examples tương tự
    RAG-->>API: RAGContext {schema_chunks, examples, metrics}

    API->>PB: build_prompt(system_rules, rag_context, question)
    PB-->>API: Full prompt + tool definitions

    API->>Claude: messages.create(prompt, tools=[execute_sql, ...])

    Note over Claude: REASON: Phân tích câu hỏi<br/>→ Cần bảng sales + merchants<br/>→ Metric "doanh thu" = SUM(total_amount)<br/>→ "quý trước" = DATE_TRUNC

    Claude->>API: tool_use: execute_sql(sql="SELECT m.name, SUM(s.total_amount)...")
    API->>PG: Execute SQL (read-only, timeout 30s)
    PG-->>API: ResultSet (10 rows)
    API->>Claude: tool_result: {columns: [...], rows: [...], row_count: 10}

    Note over Claude: REASON: Kết quả hợp lệ<br/>→ Sinh giải thích cho user

    Claude-->>API: Response: SQL + explanation
    API-->>User: {sql, results, explanation}
```

---

## Diagram 2: Multi-Tool Interaction

Khi câu hỏi phức tạp, Claude có thể gọi **nhiều tools liên tiếp** trước khi sinh SQL cuối cùng.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant RAG as RAG Retrieval Module
    participant Claude as Claude Sonnet (Agent)
    participant VS as Vector Store
    participant SL as Semantic Layer
    participant PG as PostgreSQL

    User->>API: "So sánh doanh thu và tỷ lệ hoàn tiền<br/>giữa các khu vực tháng trước"
    API->>RAG: retrieve_context(question)
    RAG-->>API: RAGContext (initial schema + examples)
    API->>Claude: messages.create(prompt + tools)

    Note over Claude: REASON: Câu hỏi cần 2 metrics<br/>+ dimension "khu vực"<br/>→ RAG context chưa rõ bảng nào chứa "khu vực"

    rect rgb(255, 243, 224)
        Note right of Claude: Tool call 1: search_schema
        Claude->>API: tool_use: search_schema("khu vực region area")
        API->>VS: vector search("khu vực region area")
        VS-->>API: schema chunk: merchants.city, branches.city
        API->>Claude: tool_result: "merchants.city (khu vực merchant),<br/>branches.city (khu vực chi nhánh)"
    end

    Note over Claude: REASON: "khu vực" = merchants.city<br/>→ Cần resolve metric "doanh thu" và "tỷ lệ hoàn tiền"

    rect rgb(243, 229, 245)
        Note right of Claude: Tool call 2: get_metric_definition
        Claude->>API: tool_use: get_metric_definition("doanh thu")
        API->>SL: lookup("doanh thu")
        SL-->>API: {sql: "SUM(sales.total_amount)", filter: "status='completed'"}
        API->>Claude: tool_result: doanh_thu definition
    end

    rect rgb(243, 229, 245)
        Note right of Claude: Tool call 3: get_metric_definition
        Claude->>API: tool_use: get_metric_definition("tỷ lệ hoàn tiền")
        API->>SL: lookup("tỷ lệ hoàn tiền")
        SL-->>API: {sql: "COUNT(refunds.id)::FLOAT / NULLIF(COUNT(sales.id), 0)"}
        API->>Claude: tool_result: refund_rate definition
    end

    Note over Claude: REASON: Đã có đủ thông tin<br/>→ Sinh SQL với JOIN sales + merchants + refunds

    rect rgb(232, 245, 233)
        Note right of Claude: Tool call 4: execute_sql
        Claude->>API: tool_use: execute_sql("SELECT m.city, SUM(s.total_amount)...")
        API->>PG: Execute SQL
        PG-->>API: ResultSet (5 rows)
        API->>Claude: tool_result: {rows: [...]}
    end

    Note over Claude: REASON: Sinh giải thích so sánh<br/>giữa các khu vực

    Claude-->>API: Response: SQL + kết quả + giải thích so sánh
    API-->>User: {sql, results, explanation}
```

---

## Diagram 3: Error Recovery (LLM Self-Correction)

Khi SQL bị lỗi, Claude **tự đọc error message** và **tự sửa SQL** — không có code-based validator.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant Claude as Claude Sonnet (Agent)
    participant PG as PostgreSQL

    User->>API: "Tổng doanh thu theo loại sản phẩm"
    API->>Claude: messages.create(prompt + tools)

    Note over Claude: REASON: Cần bảng sales + products<br/>→ Sinh SQL

    rect rgb(255, 235, 238)
        Note right of Claude: Lần 1: SQL có lỗi
        Claude->>API: tool_use: execute_sql(<br/>"SELECT product_type, SUM(total_amount)..."<br/>)
        API->>PG: Execute SQL
        PG-->>API: ERROR: column "product_type" does not exist
        API->>Claude: tool_result: {error: "column 'product_type'<br/>does not exist"}
    end

    Note over Claude: OBSERVE: Column sai tên<br/>→ Có thể là "product_category"<br/>hoặc cần check schema

    rect rgb(255, 243, 224)
        Note right of Claude: Gọi tool để verify column name
        Claude->>API: tool_use: search_schema("product type category")
        API-->>Claude: tool_result: "products.product_category_id,<br/>product_categories.category_name"
    end

    Note over Claude: REASON: Cần JOIN products + product_categories<br/>→ Sửa SQL

    rect rgb(232, 245, 233)
        Note right of Claude: Lần 2: SQL đã sửa
        Claude->>API: tool_use: execute_sql(<br/>"SELECT pc.category_name, SUM(s.total_amount)...<br/>JOIN products p ON s.product_id = p.id<br/>JOIN product_categories pc ON p.product_category_id = pc.id..."<br/>)
        API->>PG: Execute SQL
        PG-->>API: ResultSet (8 rows)
        API->>Claude: tool_result: {columns: [...], rows: [...]}
    end

    Note over Claude: Kết quả OK → Sinh giải thích

    Claude-->>API: Response: SQL (đã sửa) + kết quả + giải thích
    API-->>User: {sql, results, explanation}

    Note over User, PG: LƯU Ý: Không có code validator kiểm tra trước.<br/>LLM tự phát hiện lỗi từ DB error message.<br/>Không có hard limit retry — phụ thuộc LLM judgment.
```

---

## Diagram 4: Streaming Flow

Streaming qua WebSocket — token được stream realtime, tạm dừng khi tool call, tiếp tục sau khi tool trả kết quả.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant WS as WebSocket
    participant RAG as RAG Retrieval Module
    participant Claude as Claude API (Streaming)
    participant PG as PostgreSQL

    User->>WS: ws://connect + gửi câu hỏi
    WS->>RAG: retrieve_context(question)
    RAG-->>WS: RAGContext

    WS->>Claude: messages.create(stream=True, prompt, tools)

    rect rgb(232, 245, 233)
        Note over Claude, WS: Streaming Phase 1: LLM reasoning
        Claude-->>WS: stream token: "Tôi sẽ truy vấn..."
        WS-->>User: "Tôi sẽ truy vấn..."
        Claude-->>WS: stream token: "...dữ liệu doanh thu..."
        WS-->>User: "...dữ liệu doanh thu..."
    end

    rect rgb(255, 243, 224)
        Note over Claude, PG: Tool Call — Stream tạm dừng
        Claude-->>WS: tool_use: execute_sql(...)
        WS->>PG: Execute SQL (read-only)
        Note over WS, User: Gửi status: "Đang truy vấn database..."
        WS-->>User: [status: executing_query]
        PG-->>WS: ResultSet
        WS->>Claude: tool_result: {rows: [...]}
    end

    rect rgb(232, 245, 233)
        Note over Claude, WS: Streaming Phase 2: Explanation
        Claude-->>WS: stream token: "Kết quả cho thấy..."
        WS-->>User: "Kết quả cho thấy..."
        Claude-->>WS: stream token: "...Merchant A dẫn đầu với..."
        WS-->>User: "...Merchant A dẫn đầu với..."
        Claude-->>WS: stream token: "...50 triệu đồng doanh thu."
        WS-->>User: "...50 triệu đồng doanh thu."
    end

    Claude-->>WS: [end_turn]
    WS-->>User: {complete: true, sql: "...", results: {...}}
```

**Lưu ý về streaming:**
- **Phase 1 (reasoning):** Tokens stream liên tục cho user thấy "agent đang suy nghĩ"
- **Tool call:** Stream tạm dừng. Application gửi status message ("đang truy vấn database...")
- **Phase 2 (explanation):** Stream tiếp tục với giải thích kết quả
- Perceived latency giảm đáng kể: user thấy response sau ~1s thay vì đợi 5-6s

---

## Diagram 5: Out-of-scope Handling

Không có Router riêng — LLM tự xác định câu hỏi nằm ngoài phạm vi dựa trên system prompt rules.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant RAG as RAG Retrieval Module
    participant VS as Vector Store
    participant Claude as Claude Sonnet (Agent)

    User->>API: "Thời tiết hôm nay thế nào?"

    API->>RAG: retrieve_context(question)
    RAG->>VS: vector search("thời tiết hôm nay")
    VS-->>RAG: Low similarity scores (< 0.3)
    Note over RAG: Kết quả retrieval không liên quan<br/>nhưng vẫn trả về (không có Router filter)
    RAG-->>API: RAGContext {schema_chunks: [...], examples: [...]}

    API->>Claude: messages.create(prompt + tools)

    Note over Claude: System prompt rule:<br/>"Chỉ trả lời câu hỏi liên quan đến<br/>dữ liệu Banking/POS trong database.<br/>Nếu câu hỏi ngoài phạm vi,<br/>từ chối lịch sự."

    Note over Claude: REASON: "thời tiết" không liên quan<br/>đến Banking/POS data<br/>→ Từ chối lịch sự

    Claude-->>API: "Xin lỗi, tôi chỉ có thể giúp bạn truy vấn<br/>dữ liệu liên quan đến hệ thống Banking/POS.<br/>Ví dụ, bạn có thể hỏi:<br/>- Doanh thu tháng này bao nhiêu?<br/>- Top 10 merchant hoạt động nhiều nhất?<br/>- Phân bố KYC status của khách hàng?"

    API-->>User: {type: "out_of_scope", message: "..."}

    Note over User, Claude: SO SÁNH VỚI PATTERN 1:<br/>Pattern 1: Router (code) detect ngay = fast, deterministic, 0 LLM cost<br/>Pattern 2: LLM phải xử lý = chậm hơn, tốn token, có thể sai<br/><br/>Rủi ro: LLM có thể cố trả lời thay vì từ chối,<br/>đặc biệt với câu hỏi mơ hồ (borderline cases)
```

---

## Tổng Kết: So Sánh Actors Giữa Các Diagram

| Diagram | Pattern 1 Actors | Pattern 2 Actors | Giảm |
|---------|-----------------|-----------------|------|
| **Happy Path** | User, API, Router, Schema Linker, Vector Store, SQL Generator, Claude, Validator, Executor, PostgreSQL, Insight | User, API, RAG Module, Vector Store, Prompt Builder, Claude, PostgreSQL | **11 → 7** |
| **Error Recovery** | Generator, Validator (code loop, max 3 retries) | Claude tự retry (không giới hạn bằng code) | Code-controlled → LLM-controlled |
| **Out-of-scope** | Router (code) detect ngay, 0 LLM cost | Claude (LLM) phải xử lý, tốn 1 API call | Deterministic → Probabilistic |
