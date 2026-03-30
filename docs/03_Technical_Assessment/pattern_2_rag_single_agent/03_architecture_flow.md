# Luồng Architecture Tổng Thể — RAG-Enhanced Single Agent (BIRD Multi-Database)

## 1. Kiến Trúc Tổng Thể

Pattern 2 giữ kiến trúc **đơn giản** với 2 components chính (RAG Retrieval + Single LLM Agent), mở rộng cho **multi-database** sử dụng BIRD-SQL benchmark. Điểm khác biệt chính: mọi luồng xử lý đều **db_id aware** — từ RAG retrieval đến tool execution.

```mermaid
graph TB
    subgraph Presentation["LAYER 1: PRESENTATION"]
        User["Người dùng"]
        API["REST API /api/query"]
        WS["WebSocket (streaming)"]
        StreamlitUI["Streamlit Chat UI<br/>+ Database Selector"]
    end

    subgraph AgentCore["LAYER 2: AGENT CORE"]
        subgraph RAGModule["RAG Retrieval Module [code] — db_id aware"]
            Embed["Embed câu hỏi"]
            SchemaSearch["Vector search schema<br/>filter: db_id"]
            ExampleSearch["Vector search examples<br/>filter: db_id + split=train"]
            EvidenceLookup["Lookup evidence<br/>from BIRD"]
        end

        PromptBuilder["Build Prompt<br/>System + Schema + Evidence + Examples + Question"]

        subgraph LLMAgent["Single LLM Agent [Claude Sonnet]"]
            Reason["Reason: Phân tích câu hỏi"]
            Generate["Generate: Sinh SQL (SQLite syntax)"]
            ToolCall["Act: Gọi tools"]
            Explain["Explain: Giải thích kết quả"]
        end
    end

    subgraph Knowledge["LAYER 3: KNOWLEDGE"]
        VectorStore["ChromaDB<br/>Schema embeddings (per db_id)"]
        ExampleStore["Example Store<br/>BIRD train split (per db_id)"]
        EvidenceStore["Evidence Store<br/>BIRD evidence (per question)"]
    end

    subgraph DataAccess["LAYER 4: DATA ACCESS"]
        DBRegistry["Database Registry<br/>db_id → SQLite path"]
        ExecTool["Tool: execute_sql → SQLite"]
        SearchTool["Tool: search_schema"]
        EnumTool["Tool: get_column_values"]
        AuditLog["Audit Logger"]
    end

    subgraph Data["LAYER 5: DATA"]
        SQLite["SQLite Databases<br/>BIRD benchmark (70+ DBs)"]
        ChromaDB["ChromaDB"]
    end

    User -->|"question + db_id"| StreamlitUI
    StreamlitUI --> API
    API --> RAGModule
    RAGModule --> VectorStore
    RAGModule --> ExampleStore
    RAGModule --> EvidenceStore
    RAGModule -->|"RAGContext (db-specific)"| PromptBuilder
    PromptBuilder -->|"Full prompt + tools"| LLMAgent
    LLMAgent <-->|"Tool calls"| ExecTool
    LLMAgent <-->|"Tool calls"| SearchTool
    LLMAgent <-->|"Tool calls"| EnumTool
    ExecTool -->|"route by db_id"| DBRegistry
    DBRegistry --> SQLite
    ExecTool --> AuditLog
    SearchTool --> VectorStore
    LLMAgent -->|"Response"| API
    API -->|"SQL + Data + Giải thích"| WS
    WS --> User

    style LLMAgent fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    style RAGModule fill:#f3e5f5,stroke:#7b1fa2
    style DataAccess fill:#fff3e0,stroke:#ef6c00
    style DBRegistry fill:#fff9c4,stroke:#f9a825,stroke-width:2px
```

---

## 2. Luồng Xử Lý Chính — 6 Bước

```mermaid
graph LR
    S1["1. User gửi<br/>question + db_id"]
    S2["2. RAG Retrieval<br/>[code] — filter db_id"]
    S3["3. Build Prompt<br/>[code] — SQLite syntax"]
    S4["4. Claude API<br/>(single call + tools)"]
    S5["5. Tool Use Cycle<br/>(execute on SQLite)"]
    S6["6. Response<br/>SQL + Data + Explanation"]

    S1 --> S2 --> S3 --> S4 --> S5 --> S6

    style S2 fill:#f3e5f5,stroke:#7b1fa2
    style S4 fill:#e1f5fe,stroke:#0288d1,stroke-width:2px
    style S5 fill:#fff3e0,stroke:#ef6c00
```

### Bước 1: User gửi câu hỏi + db_id

```
POST /api/query
{
  "question": "List publishers with sales less than 10000",
  "db_id": "video_games"
}
```

`db_id` xác định database target. Trong evaluation mode, `db_id` lấy từ BIRD dataset. Trong interactive mode, user chọn từ dropdown.

### Bước 2: RAG Retrieval Module [code] — db_id filtered

Code thực hiện vector search **có filter theo db_id**:

```
Input:  question="List publishers with sales less than 10000"
        db_id="video_games"
        ↓
        embed(question) → vector [0.12, -0.45, 0.78, ...]
        ↓
Output: {
  schema_chunks: [
    "CREATE TABLE publisher (id INTEGER pk, publisher_name TEXT ...)",
    "CREATE TABLE game_publisher (id INTEGER pk, game_id INTEGER FK, publisher_id INTEGER FK ...)",
    "CREATE TABLE game_platform (id INTEGER pk, game_publisher_id INTEGER FK, platform_id INTEGER FK, release_year INTEGER ...)",
    "CREATE TABLE region_sales (region_id INTEGER, game_platform_id INTEGER FK, num_sales REAL ...)"
  ],
  examples: [
    {q: "How many games in each genre?", sql: "SELECT g.genre_name, COUNT(*) ..."},
    {q: "What are the top 5 platforms by number of games?", sql: "SELECT p.platform_name ..."}
  ],
  evidence: "num_sales < 0.1 means less than 10000; publisher refers to publisher_name"
}
```

**Điểm khác biệt:** Tất cả results đều thuộc `db_id="video_games"`. Không trộn lẫn schema/examples từ databases khác.

### Bước 3: Build Prompt [code]

Ghép context thành prompt, **SQLite syntax** thay vì PostgreSQL:

```
System Prompt = [
  System Rules (SELECT only, LIMIT, SQLite syntax, output format),
  Database Schema (từ bước 2 — CREATE TABLE statements),
  Evidence (từ BIRD — domain hints),
  Few-shot Examples (từ bước 2 — BIRD train split)
]

User Message = "List publishers with sales less than 10000"

Tool Definitions = [execute_sql, search_schema, get_column_values]
```

### Bước 4: Gửi tới Claude API (single call, với tool definitions)

Một API call duy nhất tới Claude:
- System prompt chứa schema của `video_games` database
- User message là câu hỏi
- Tool definitions (3 tools)

Claude xử lý tất cả trong call này: phân tích câu hỏi, chọn bảng, sinh SQL.

### Bước 5: Tool Use Cycle — Execute trên SQLite

Claude gọi tools, application route tới đúng SQLite file:

```mermaid
graph TD
    Claude1["Claude sinh SQL (SQLite syntax)"]
    ToolCall["tool_use: execute_sql(sql=...)"]
    Route["Application: lookup db_id → SQLite path"]
    Exec["SQLite: Execute SQL (read-only)"]
    ToolResult["tool_result → gửi lại Claude"]
    Claude2["Claude giải thích kết quả"]

    Claude1 -->|"tool_use block"| ToolCall
    ToolCall --> Route
    Route -->|"video_games.sqlite"| Exec
    Exec -->|"ResultSet"| ToolResult
    ToolResult --> Claude2

    style Claude1 fill:#e1f5fe,stroke:#0288d1
    style Claude2 fill:#e1f5fe,stroke:#0288d1
    style Route fill:#fff9c4,stroke:#f9a825,stroke-width:2px
    style Exec fill:#e8f5e9,stroke:#2e7d32
```

**Routing logic:**
1. Claude gọi `execute_sql(sql="SELECT ...")`
2. Application code (không phải LLM) lookup `db_id` từ session context
3. Database Registry trả về path: `data/bird/databases/video_games/video_games.sqlite`
4. SQL executed trên SQLite file đó (read-only mode)
5. Result gửi lại cho Claude

### Bước 6: Response

```json
{
  "db_id": "video_games",
  "sql": "SELECT T.publisher_name FROM (SELECT DISTINCT T5.publisher_name FROM region AS T1 INNER JOIN game_platform AS T2 ON T1.id = T2.id INNER JOIN game_publisher AS T3 ON T2.game_publisher_id = T3.id INNER JOIN publisher AS T5 ON T3.publisher_id = T5.id WHERE T1.num_sales < 0.1) T LIMIT 5",
  "results": {
    "columns": ["publisher_name"],
    "rows": [["Acclaim Entertainment"], ["Activision"], ...],
    "row_count": 5
  },
  "explanation": "Here are 5 publishers whose games had sales numbers less than 10,000 (num_sales < 0.1)..."
}
```

---

## 3. Luồng Evaluation — Đánh Giá Accuracy

Flow bổ sung chạy song song hoặc sau khi hệ thống hoạt động:

```mermaid
graph TB
    subgraph Input["INPUT"]
        TestSet["BIRD Test Split<br/>(~90% examples)"]
    end

    subgraph Pipeline["EVALUATION PIPELINE"]
        Loop["For each (question, db_id, ground_truth_sql):"]
        Agent["Run Agent Pipeline<br/>(RAG → Prompt → Claude → Tools)"]
        ExecGen["Execute generated_sql<br/>trên SQLite"]
        ExecGT["Execute ground_truth_sql<br/>trên SQLite"]
        Compare["Compare result sets<br/>set(generated) == set(expected)?"]
    end

    subgraph Output["OUTPUT"]
        Report["Evaluation Report<br/>• Overall EX accuracy<br/>• Per-DB accuracy<br/>• Error breakdown<br/>• Avg latency"]
    end

    TestSet --> Loop
    Loop --> Agent
    Agent --> ExecGen
    Loop --> ExecGT
    ExecGen --> Compare
    ExecGT --> Compare
    Compare --> Report

    style Input fill:#fff9c4,stroke:#f9a825
    style Pipeline fill:#e1f5fe,stroke:#0288d1
    style Output fill:#e8f5e9,stroke:#2e7d32
```

**Evaluation flow chi tiết:**

```
[1] Load test_split.json
    └── Filter: examples KHÔNG có trong train split

[2] For each test example:
    ├── Input: {question, db_id, ground_truth_sql, evidence (optional)}
    │
    ├── [2a] Run qua Agent pipeline
    │   ├── RAG Retrieval (db_id filtered, train examples only)
    │   ├── Build Prompt (SQLite, with/without evidence)
    │   ├── Claude generates SQL
    │   └── Output: generated_sql
    │
    ├── [2b] Execute generated_sql trên db_id.sqlite
    │   └── generated_result (or error)
    │
    ├── [2c] Execute ground_truth_sql trên db_id.sqlite
    │   └── expected_result
    │
    └── [2d] Compare
        ├── MATCH: set(generated_result) == set(expected_result)
        ├── MISMATCH: results khác nhau
        └── ERROR: generated_sql syntax/runtime error

[3] Aggregate results → EvalReport
```

---

## 4. Luồng Data Pipeline — Setup Ban Đầu

Chạy một lần để chuẩn bị knowledge base:

```mermaid
graph TB
    subgraph Download["DOWNLOAD"]
        HF["HuggingFace Dataset<br/>xu3kev/BIRD-SQL-data-train"]
        BirdDB["BIRD SQLite Files<br/>70+ databases"]
    end

    subgraph Process["PROCESS"]
        Parse["Parse examples<br/>group by db_id"]
        Split["Train/Test Split<br/>per database"]
        Chunk["Chunk schemas<br/>per database"]
    end

    subgraph Index["INDEX"]
        IdxSchema["Index schema chunks<br/>→ ChromaDB (schema_chunks)"]
        IdxExamples["Index train examples<br/>→ ChromaDB (examples)"]
        BuildReg["Build Database Registry<br/>db_id → SQLite path"]
    end

    subgraph Verify["VERIFY"]
        V1["Verify: test examples NOT indexed"]
        V2["Verify: all db_ids have SQLite files"]
        V3["Verify: retrieval works per db_id"]
    end

    HF --> Parse
    BirdDB --> BuildReg
    Parse --> Split
    Split --> Chunk
    Chunk --> IdxSchema
    Split -->|"train only"| IdxExamples
    IdxSchema --> V1
    IdxExamples --> V1
    BuildReg --> V2
    V1 --> V3

    style Download fill:#fff9c4,stroke:#f9a825
    style Process fill:#f3e5f5,stroke:#7b1fa2
    style Index fill:#e1f5fe,stroke:#0288d1
    style Verify fill:#e8f5e9,stroke:#2e7d32
```

---

## 5. Rủi Ro Kiến Trúc

Giữ nguyên rủi ro từ Pattern 2 single-agent, thêm rủi ro mới từ multi-database:

```mermaid
graph TB
    subgraph Risks["RỦI RO"]
        R1["Prompt quá dài<br/>Schema lớn + Evidence + Examples"]
        R2["Schema diversity<br/>70+ DB schemas rất khác nhau<br/>→ LLM có thể confused"]
        R3["SQLite syntax<br/>BIRD SQL có thể dùng SQLite-specific<br/>features LLM không quen"]
        R4["Train/test leak<br/>Nếu test examples lọt vào<br/>train → eval không chính xác"]
        R5["Database mismatch<br/>db_id routing sai → query DB sai"]
    end

    subgraph Mitigations["GIẢM THIỂU"]
        M1["Dynamic chunking<br/>Chỉ top_k relevant chunks, không full schema"]
        M2["Per-DB few-shot examples<br/>Giúp LLM học pattern SQL per DB"]
        M3["System prompt enforce SQLite<br/>+ Evidence cung cấp domain hints"]
        M4["Split verification pipeline<br/>Kiểm tra overlap khi index"]
        M5["Registry validation<br/>Verify db_id → path mapping trước khi execute"]
    end

    R1 --> M1
    R2 --> M2
    R3 --> M3
    R4 --> M4
    R5 --> M5

    style Risks fill:#ffebee,stroke:#c62828
    style Mitigations fill:#e8f5e9,stroke:#2e7d32
```

---

## 6. So Sánh: Single-DB Banking vs Multi-DB BIRD

| Khía cạnh | Single-DB (Banking) | Multi-DB (BIRD) |
|-----------|-------------------|-----------------|
| **Database engine** | PostgreSQL | SQLite |
| **Số databases** | 1 | 70+ |
| **Schema source** | `data/schema.json` (cố định) | BIRD DDL per database (dynamic) |
| **Chunking** | 7 hardcoded domain clusters | Dynamic per database |
| **Examples** | 40 golden queries cố định | 9,430+ từ BIRD (train/test split) |
| **Domain knowledge** | Semantic Layer (metrics, aliases) | BIRD Evidence (per question) |
| **SQL syntax** | PostgreSQL | SQLite |
| **API contract** | `{question}` | `{question, db_id}` |
| **Tool routing** | Fixed connection pool | Database Registry → SQLite |
| **Evaluation** | Không có | Execution Accuracy framework |
| **Mục tiêu** | Demo Banking/POS | Benchmark Text-to-SQL accuracy |
