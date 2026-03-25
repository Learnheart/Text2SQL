# Tiến hóa Công nghệ Text-to-SQL
### Technology Evolution: Pre-2025 vs 2025+ | Q1/2026

---

## 1. TIMELINE TIẾN HÓA

```
2016        2018        2020        2022        2024        2026
  |           |           |           |           |           |
  Rule-based  Seq2Seq     PLM-based   LLM Prompting  Agentic AI
  Templates   Neural      BERT/T5     GPT-4/Claude   Multi-Agent
              Models      Fine-tune   Few-shot       RAG + Tools
```

---

## 2. GIAI ĐOẠN 1: TRƯỚC NĂM 2025

### 2.1 Rule-based / Template Matching (Pre-2017)
| Khía cạnh | Chi tiết |
|-----------|----------|
| **Cách tiếp cận** | Ánh xạ keyword → SQL template thủ công |
| **Ưu điểm** | Dự đoán được, không cần training data |
| **Nhược điểm** | Brittle, chi phí nhân công cao, không generalize |
| **Đại diện** | NaLIR, hệ thống NLQ đời đầu |

### 2.2 Seq2Seq Neural Models (2017-2019)
| Khía cạnh | Chi tiết |
|-----------|----------|
| **Cách tiếp cận** | Encoder-decoder architecture, attention mechanism |
| **Ưu điểm** | Tự học patterns từ data |
| **Nhược điểm** | Cross-domain kém, vocab giới hạn |
| **Đại diện** | Seq2SQL, SQLNet, IRNet, HydraNet, TypeSQL |

### 2.3 Pre-trained Language Models (2019-2022)
| Khía cạnh | Chi tiết |
|-----------|----------|
| **Cách tiếp cận** | Fine-tune BERT/T5 trên Text-to-SQL datasets |
| **Ưu điểm** | Generalize tốt hơn, transfer learning |
| **Nhược điểm** | Vẫn cần fine-tune per domain |
| **Đại diện** | PICARD, RESDSQL, BRIDGE |

### 2.4 LLM Prompting / Few-shot (2022-2024)
| Khía cạnh | Chi tiết |
|-----------|----------|
| **Cách tiếp cận** | In-context learning với GPT-4/Claude, few-shot examples |
| **Ưu điểm** | Accuracy cao trên benchmarks, không cần fine-tune |
| **Nhược điểm** | API cost cao, hallucination risk, latency |
| **Đại diện** | DIN-SQL, DAIL-SQL, C3SQL |
| **Accuracy** | DAIL-SQL: 86.6% EX trên Spider |

### 2.5 Fine-tuned Open LLMs (2023-2024)
| Khía cạnh | Chi tiết |
|-----------|----------|
| **Cách tiếp cận** | Fine-tune CodeLlama/StarCoder trên SQL datasets |
| **Ưu điểm** | Deploy local, cost-effective, competitive với GPT-3.5 |
| **Nhược điểm** | Hạn chế trên complex queries |
| **Đại diện** | SQLCoder (15B), CodeS, Chat2DB-SQL-7B |

---

## 3. GIAI ĐOẠN 2: TỪ 2025 TRỞ LẠI ĐÂY

### 3.1 LLM Agents & Multi-Agent Systems

**Bước nhảy vọt:** Từ single-shot generation → agentic workflows với multiple specialized agents.

| Framework | Đặc điểm | Kết quả |
|-----------|----------|---------|
| **MARS-SQL** | Multi-Agent RL: agents chuyên biệt + interactive RL cho verification | State-of-the-art trên complex queries |
| **ReFoRCE** | Dẫn đầu Spider 2.0 leaderboard | 35.83% (Snow), 36.56% (Lite); hiệu quả chỉ 3.52 LLM calls/example |
| **Snowflake Intelligence** | Production agentic framework, GA | 90-95% trên verified repos |
| **Databricks Agent Bricks** | Declarative agent definition | Tích hợp Unity Catalog |

**Kiến trúc Agentic tiêu biểu:**
```
User Query
    ↓
[Router Agent] → Phân loại: SQL query / chart / clarification?
    ↓
[Schema Linker Agent] → Xác định tables/columns liên quan
    ↓
[SQL Generator Agent] → Sinh SQL (có thể nhiều candidates)
    ↓
[Validator Agent] → Kiểm tra syntax, execute, verify results
    ↓
[Self-Correction Loop] → Nếu lỗi → quay lại Generator với feedback
    ↓
[Insight Agent] → Phân tích kết quả, sinh narrative
```

### 3.2 RAG-Augmented SQL Generation

| Kỹ thuật | Mô tả |
|----------|--------|
| **Schema metadata retrieval** | Retrieve column descriptions, sample values, business glossary |
| **Similar query retrieval** | Tìm SQL examples tương tự từ query history |
| **Knowledge Graph augmentation** | Structured retrieval layer cho outcomes deterministic hơn |
| **Hybrid retrieval** | Vector search + keyword search + graph traversal |

**Xu hướng đáng chú ý:** Context window expansion (1-2M tokens trong 2025-2026) thách thức giả định RAG — direct context processing đôi khi tốt hơn complex retrieval cho schema nhỏ/trung bình.

### 3.3 Semantic Layer-First Architecture

```
                    ┌─────────────────────┐
                    │   Semantic Layer     │
                    │  (Business Metrics,  │
                    │   Dimensions, Rules) │
                    └──────────┬──────────┘
                               │
              ┌────────────────┼────────────────┐
              ↓                ↓                ↓
        [NL-to-SQL]      [Governance]     [Consistency]
        LLM sinh SQL     Enforce access   Cùng metric
        dựa trên         control tại      definition
        semantic model   query level      across tools
```

**Insight quan trọng:** Snowflake đạt 90-95% accuracy nhờ **metadata curation** chứ không phải nhờ LLM giỏi hơn. Đây là bài học then chốt cho dự án.

### 3.4 MCP (Model Context Protocol) Ecosystem

- **DBHub**: Universal database MCP server (100K+ downloads).
- Cho phép bất kỳ MCP-compatible AI assistant (Claude, Cursor, VS Code) query databases.
- Tạo paradigm mới: không cần build custom integration cho từng tool.

---

## 4. BENCHMARK LANDSCAPE

### 4.1 Các Benchmark Chính

| Benchmark | Năm | Mô tả | SOTA | Nhận xét |
|-----------|-----|--------|------|----------|
| **WikiSQL** | 2017 | Single-table, queries đơn giản | >90% EX | Đã deprecated cho research |
| **Spider** | 2018 | 200 DBs, cross-domain | **~91.2% EX** | Coi như "solved" cho academic |
| **BIRD** | 2023 | Real-world DBs + external knowledge | ~77.5% EX | BIRD 2025 mở rộng 4-6 benchmarks mới |
| **Spider 2.0** | 2025 (ICLR Oral) | Enterprise-scale, 3000+ columns, multi-dialect | **~36% EX** | Phản ánh gap thực tế |
| **LiveSQLBench** | 2025 | Contamination-free, full SQL spectrum | ~45% (o3-mini) | Chống data leakage |
| **BIRD-Interact** | 2026 (ICLR Oral) | Interactive multi-turn | -- | Conversational SQL generation |
| **MultiSpider 2.0** | 2025 | Non-English Spider 2.0 | **~4-6% EX** | Multilingual gap rất lớn |

### 4.2 Cảnh báo về Benchmark Quality
Paper CIDR 2026 "Text-to-SQL Benchmarks are Broken" phát hiện:
- Annotation errors trong benchmarks phổ biến.
- Model performance bị đánh giá sai từ -3% đến +31%.
- Rank shifts lên đến 3 vị trí sau khi sửa lỗi annotation.

### 4.3 Bài học cho Dự án

| Gap | Ý nghĩa thực tế |
|-----|-----------------|
| Spider ~91% vs Spider 2.0 ~36% | Academic benchmark ≠ production reality |
| MultiSpider 2.0 ~4-6% | Vietnamese NLQ là thách thức rất lớn |
| LiveSQLBench ~45% | Ngay cả model tốt nhất cũng chỉ đạt ~45% trên benchmark sạch |
| Snowflake 90-95% (verified) | Metadata curation là chìa khóa, không phải model |

---

## 5. TECHNICAL CHALLENGES CHÍNH

### 5.1 Schema Linking (Bottleneck #1)
- Enterprise DBs: hàng trăm đến hàng ngàn tables/columns.
- **LinkAlign** (EMNLP 2025) giải quyết scalable schema linking.
- Schema retrieval performance tương quan trực tiếp với accuracy.

### 5.2 Complex Query Generation
- CTEs, window functions, subqueries, cross-database joins.
- Spider 2.0 ~36% vs Spider 1.0 ~91% = enterprise complexity gap.

### 5.3 Ambiguous Queries
- "Tổng doanh thu" = revenue? units? net-of-returns?
- Semantic layer + human-in-the-loop là giải pháp.

### 5.4 Security Risks
- **Zero-Knowledge Schema Inference Attacks** (NAACL 2025): Text-to-SQL có thể leak schema info.
- Giải pháp: metadata-only processing, query-level governance.

### 5.5 Multilingual (Vietnamese)
- MultiSpider 2.0: ~4-6% accuracy cho non-English.
- Cần đầu tư vào Vietnamese NLP + custom training data.

---

## 6. KHUYẾN NGHỊ CÔNG NGHỆ CHO DỰ ÁN

Dựa trên phân tích xu hướng, **kiến trúc đề xuất** cho dự án Text2SQL:

| Component | Khuyến nghị | Lý do |
|-----------|-------------|-------|
| **Architecture** | RAG + Agentic (multi-step) | Production-proven; self-correction loop |
| **LLM** | Claude API (primary) + local fallback | Accuracy cao; Claude hỗ trợ tool use tốt |
| **Vector DB** | ChromaDB → Qdrant (production) | Đã có ChromaDB; Qdrant cho scale |
| **Embedding** | bge-large-en-v1.5 (hiện tại) → multilingual model | Đã tích hợp; cần upgrade cho Vietnamese |
| **Semantic Layer** | Custom metadata layer trên schema.json | Key to 90%+ accuracy |
| **Database** | PostgreSQL + pgvector | Đã setup; production-ready |
| **Execution** | Read-only connection + sandboxed | Security requirement |
| **UI** | Chat interface (web) | Adoption dễ nhất |

---

*Nguồn: Spider benchmark, ICLR 2025/2026, EMNLP 2025, NAACL 2025, VLDB 2025, CIDR 2026, Snowflake, Databricks*
*Ngày cập nhật: 25/03/2026 | Phiên bản: 1.0*
