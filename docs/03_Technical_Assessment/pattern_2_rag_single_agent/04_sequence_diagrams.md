# Sequence Diagrams — RAG-Enhanced Single Agent (BIRD Multi-Database)

## Diagram 1: E2E Happy Path — Multi-Database Query

User hỏi về một database cụ thể (thông qua `db_id`), agent sinh SQL SQLite, execute trên đúng database.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant RAG as RAG Retrieval Module
    participant VS as Vector Store (ChromaDB)
    participant PB as Prompt Builder
    participant Claude as Claude Sonnet (Agent)
    participant DR as Database Registry
    participant SQLite as SQLite DB

    User->>API: POST /api/query<br/>{"question": "List publishers with sales < 10000",<br/> "db_id": "video_games"}

    API->>RAG: retrieve_context(question, db_id="video_games")
    RAG->>VS: vector search schema_chunks<br/>where: {db_id: "video_games"}, top_k=5
    VS-->>RAG: schema chunks (publisher, game_publisher, region_sales...)
    RAG->>VS: vector search examples<br/>where: {db_id: "video_games", split: "train"}, top_k=3
    VS-->>RAG: few-shot examples (train split only)
    RAG-->>API: RAGContext {schema_chunks, examples, evidence}

    API->>PB: build_prompt(rules, rag_context, question)
    Note over PB: System prompt enforces SQLite syntax
    PB-->>API: Full prompt + tool definitions

    API->>Claude: messages.create(prompt, tools=[execute_sql, ...])

    Note over Claude: REASON: Phân tích câu hỏi<br/>→ Cần tables: publisher, region_sales,<br/>  game_publisher, game_platform<br/>→ Evidence: "num_sales < 0.1 means < 10000"<br/>→ Sinh SQLite SQL

    Claude->>API: tool_use: execute_sql(sql="SELECT DISTINCT T5.publisher_name ...")
    API->>DR: get_connection("video_games")
    DR-->>API: path: data/bird/databases/video_games/video_games.sqlite
    API->>SQLite: Execute SQL (read-only)
    SQLite-->>API: ResultSet (rows)
    API->>Claude: tool_result: {columns: ["publisher_name"], rows: [...], row_count: 5}

    Note over Claude: Kết quả hợp lệ<br/>→ Sinh giải thích

    Claude-->>API: Response: SQL + explanation
    API-->>User: {db_id, sql, results, explanation}
```

---

## Diagram 2: Multi-Tool Interaction — Schema Discovery

Câu hỏi phức tạp trên database không quen. Claude cần gọi nhiều tools để tìm hiểu schema trước khi sinh SQL.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant RAG as RAG Retrieval Module
    participant Claude as Claude Sonnet (Agent)
    participant VS as Vector Store
    participant DR as Database Registry
    participant SQLite as SQLite DB

    User->>API: "What is the average rating of restaurants<br/>that failed inspection?"<br/>db_id: "food_inspection_2"

    API->>RAG: retrieve_context(question, db_id="food_inspection_2")
    RAG-->>API: RAGContext (schema chunks + train examples)
    API->>Claude: messages.create(prompt + tools)

    Note over Claude: REASON: Cần tìm tables liên quan<br/>"rating" và "inspection" và "failed"<br/>→ RAG context chưa đủ rõ column names

    rect rgb(255, 243, 224)
        Note right of Claude: Tool call 1: search_schema
        Claude->>API: tool_use: search_schema("restaurant rating score")
        API->>VS: vector search where: {db_id: "food_inspection_2"}
        VS-->>API: schema chunk: "inspection(id, restaurant_id, score, result, ...)"
        API->>Claude: tool_result: table inspection with columns score, result
    end

    Note over Claude: REASON: "failed" → cần biết giá trị<br/>cột "result" là gì

    rect rgb(243, 229, 245)
        Note right of Claude: Tool call 2: get_column_values
        Claude->>API: tool_use: get_column_values("inspection", "result")
        API->>DR: get_connection("food_inspection_2")
        DR-->>API: SQLite connection
        API->>SQLite: SELECT DISTINCT result FROM inspection LIMIT 50
        SQLite-->>API: ["Pass", "Fail", "Pass w/ Conditions", "No Entry"]
        API->>Claude: tool_result: values: ["Pass", "Fail", "Pass w/ Conditions", ...]
    end

    Note over Claude: REASON: "failed" = result = 'Fail'<br/>→ Đã đủ thông tin, sinh SQL

    rect rgb(232, 245, 233)
        Note right of Claude: Tool call 3: execute_sql
        Claude->>API: tool_use: execute_sql(<br/>"SELECT AVG(r.rating) FROM restaurant r<br/>JOIN inspection i ON r.id = i.restaurant_id<br/>WHERE i.result = 'Fail'")
        API->>DR: get_connection("food_inspection_2")
        API->>SQLite: Execute SQL
        SQLite-->>API: ResultSet (1 row)
        API->>Claude: tool_result: {columns: ["AVG(r.rating)"], rows: [[3.2]]}
    end

    Claude-->>API: Response: SQL + "Average rating is 3.2 for failed restaurants"
    API-->>User: {db_id, sql, results, explanation}
```

---

## Diagram 3: Error Recovery — LLM Self-Correction

SQL bị lỗi do schema phức tạp. Claude đọc error, tìm hiểu thêm schema, sửa SQL.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant API as REST API
    participant Claude as Claude Sonnet (Agent)
    participant VS as Vector Store
    participant DR as Database Registry
    participant SQLite as SQLite DB

    User->>API: "Total revenue by car brand"<br/>db_id: "car_retails"
    API->>Claude: messages.create(prompt + tools)

    Note over Claude: REASON: "revenue" → sales amount<br/>"car brand" → car model brand<br/>→ Sinh SQL

    rect rgb(255, 235, 238)
        Note right of Claude: Lần 1: SQL có lỗi
        Claude->>API: tool_use: execute_sql(<br/>"SELECT brand, SUM(revenue) FROM cars GROUP BY brand")
        API->>DR: get_connection("car_retails")
        API->>SQLite: Execute SQL
        SQLite-->>API: ERROR: no such table: cars
        API->>Claude: tool_result: {error: "no such table: cars"}
    end

    Note over Claude: OBSERVE: Table "cars" không tồn tại<br/>→ Cần tìm đúng tên table

    rect rgb(255, 243, 224)
        Note right of Claude: Gọi search_schema để verify
        Claude->>API: tool_use: search_schema("car vehicle product brand")
        API->>VS: vector search where: {db_id: "car_retails"}
        VS-->>API: "CREATE TABLE products (productCode TEXT PK,<br/>productName TEXT, productLine TEXT, productScale TEXT,<br/>productVendor TEXT, buyPrice REAL, MSRP REAL)"<br/>"CREATE TABLE orderdetails (orderNumber INTEGER,<br/>productCode TEXT, quantityOrdered INTEGER,<br/>priceEach REAL, orderLineNumber INTEGER)"
        API->>Claude: tool_result: tables products + orderdetails
    end

    Note over Claude: REASON: "brand" = productVendor<br/>"revenue" = SUM(quantityOrdered * priceEach)<br/>→ Sửa SQL

    rect rgb(232, 245, 233)
        Note right of Claude: Lần 2: SQL đã sửa
        Claude->>API: tool_use: execute_sql(<br/>"SELECT p.productVendor, SUM(od.quantityOrdered * od.priceEach)<br/>FROM products p JOIN orderdetails od ON p.productCode = od.productCode<br/>GROUP BY p.productVendor ORDER BY 2 DESC")
        API->>DR: get_connection("car_retails")
        API->>SQLite: Execute SQL
        SQLite-->>API: ResultSet (rows)
        API->>Claude: tool_result: {columns: [...], rows: [...]}
    end

    Claude-->>API: Response: SQL (đã sửa) + kết quả + giải thích
    API-->>User: {db_id, sql, results, explanation}

    Note over User, SQLite: LLM tự phát hiện lỗi từ error message,<br/>tự tìm schema đúng, tự sửa SQL.<br/>Không có code validator riêng.
```

---

## Diagram 4: Streaming Flow

Streaming qua WebSocket với db_id context.

```mermaid
sequenceDiagram
    autonumber
    participant User as Người dùng
    participant WS as WebSocket
    participant RAG as RAG Retrieval Module
    participant Claude as Claude API (Streaming)
    participant DR as Database Registry
    participant SQLite as SQLite DB

    User->>WS: ws://connect<br/>{"question": "How many games per genre?", "db_id": "video_games"}
    WS->>RAG: retrieve_context(question, db_id="video_games")
    RAG-->>WS: RAGContext (video_games schema + train examples)

    WS->>Claude: messages.create(stream=True, prompt, tools)

    rect rgb(232, 245, 233)
        Note over Claude, WS: Streaming Phase 1: LLM reasoning
        Claude-->>WS: stream token: "I'll query the video_games database..."
        WS-->>User: "I'll query the video_games database..."
        Claude-->>WS: stream token: "...to count games per genre."
        WS-->>User: "...to count games per genre."
    end

    rect rgb(255, 243, 224)
        Note over Claude, SQLite: Tool Call — Stream tạm dừng
        Claude-->>WS: tool_use: execute_sql(...)
        WS->>DR: get_connection("video_games")
        DR-->>WS: SQLite path
        WS->>SQLite: Execute SQL (read-only)
        Note over WS, User: Gửi status: "Querying video_games database..."
        WS-->>User: [status: executing_query]
        SQLite-->>WS: ResultSet
        WS->>Claude: tool_result: {rows: [...]}
    end

    rect rgb(232, 245, 233)
        Note over Claude, WS: Streaming Phase 2: Explanation
        Claude-->>WS: stream token: "The results show..."
        WS-->>User: "The results show..."
        Claude-->>WS: stream token: "...Action genre has the most games (210)."
        WS-->>User: "...Action genre has the most games (210)."
    end

    Claude-->>WS: [end_turn]
    WS-->>User: {complete: true, db_id: "video_games", sql: "...", results: {...}}
```

---

## Diagram 5: Evaluation Flow

Chạy evaluation trên BIRD test split. Strict isolation: test examples **không bao giờ** xuất hiện trong few-shot.

```mermaid
sequenceDiagram
    autonumber
    participant Eval as Evaluation Engine
    participant TestSet as Test Split<br/>(~90% BIRD examples)
    participant Agent as Agent Pipeline<br/>(RAG → Claude → Tools)
    participant DR as Database Registry
    participant SQLite as SQLite DB
    participant Report as Eval Report

    Eval->>TestSet: Load test_split.json

    loop For each test example
        TestSet-->>Eval: {question, db_id, ground_truth_sql, evidence}

        Note over Eval: Verify: question NOT in train split

        Eval->>Agent: run(question, db_id, evidence=optional)
        Note over Agent: RAG retrieves train examples only<br/>Claude generates SQL<br/>Tools execute on SQLite
        Agent-->>Eval: {generated_sql, results, error}

        Eval->>DR: get_connection(db_id)
        DR-->>Eval: SQLite connection
        Eval->>SQLite: Execute ground_truth_sql
        SQLite-->>Eval: expected_result

        alt generated_sql executed successfully
            Eval->>SQLite: Execute generated_sql
            SQLite-->>Eval: generated_result

            alt set(generated_result) == set(expected_result)
                Note over Eval: ✓ MATCH — Execution Accuracy +1
            else Results differ
                Note over Eval: ✗ MISMATCH — Log for analysis
            end
        else generated_sql had error
            Note over Eval: ✗ ERROR — Log error type
        end

        Eval->>Report: Append result
    end

    Eval->>Report: Aggregate & generate report
    Report-->>Eval: {<br/>  overall_accuracy: 78.5%,<br/>  per_db: {video_games: 82%, car_retails: 71%, ...},<br/>  error_rate: 8.2%,<br/>  avg_latency: 4.1s<br/>}
```

---

## Diagram 6: Data Pipeline — One-time Setup

Setup flow chạy một lần để index BIRD data.

```mermaid
sequenceDiagram
    autonumber
    participant Script as Data Pipeline Script
    participant HF as HuggingFace Hub
    participant FS as File System
    participant VS as Vector Store (ChromaDB)
    participant Embed as Embedding Model

    Script->>HF: load_dataset("xu3kev/BIRD-SQL-data-train")
    HF-->>Script: 9,430+ examples {db_id, question, SQL, evidence, schema}

    Script->>FS: Download BIRD SQLite database files
    FS-->>Script: 70+ .sqlite files

    Note over Script: Group examples by db_id

    loop For each database
        Note over Script: Split examples: ~10% train, ~90% test<br/>(stratified random split)

        Script->>FS: Save train_split.json, test_split.json

        Note over Script: Extract schema DDL from examples<br/>Chunk into table groups

        loop For each schema chunk
            Script->>Embed: embed(chunk_text)
            Embed-->>Script: vector [0.12, -0.45, ...]
            Script->>VS: upsert(collection="schema_chunks",<br/>id=chunk_id, embedding=vector,<br/>metadata={db_id, tables})
        end

        loop For each train example only
            Script->>Embed: embed(question)
            Embed-->>Script: vector
            Script->>VS: upsert(collection="examples",<br/>id=example_id, embedding=vector,<br/>metadata={db_id, split="train"})
        end
    end

    Note over Script: VERIFY: No test examples in vector store
    Script->>VS: query(where={split: "test"})
    VS-->>Script: 0 results ✓

    Note over Script: VERIFY: All db_ids have SQLite files
    Script->>FS: Check data/bird/databases/{db_id}/{db_id}.sqlite
    FS-->>Script: All exist ✓

    Note over Script: Pipeline complete.<br/>Schema chunks indexed: ~1500<br/>Train examples indexed: ~940<br/>Databases registered: 70+
```

---

## Tổng Kết: So Sánh Actors

| Diagram | Actors | Mới/Thay đổi |
|---------|--------|-------------|
| **Happy Path** | User, API, RAG, VS, PB, Claude, **DB Registry**, **SQLite** | DB Registry + SQLite thay PostgreSQL |
| **Multi-Tool** | User, API, RAG, Claude, VS, **DB Registry**, **SQLite** | Tất cả tool calls route qua DB Registry |
| **Error Recovery** | User, API, Claude, VS, **DB Registry**, **SQLite** | SQLite error messages thay PostgreSQL |
| **Streaming** | User, WS, RAG, Claude, **DB Registry**, **SQLite** | db_id trong stream context |
| **Evaluation** | **Eval Engine**, **Test Set**, Agent, **DB Registry**, **SQLite**, **Report** | Hoàn toàn mới |
| **Data Pipeline** | **Pipeline Script**, **HF**, FS, VS, Embed | Hoàn toàn mới |
