# Competitive Intelligence
### Bản đồ Cạnh tranh Text-to-SQL / AI Data Agents | Q1/2026

---

## 1. COMPETITIVE LANDSCAPE MAP

```
                        ┌─────────────────────────────────────────────┐
                        │            ENTERPRISE READINESS              │
                        │                   HIGH                       │
                        │                                              │
              ┌─────────┤  Snowflake Cortex  ●  Databricks Genie      │
              │         │           ●  Microsoft Fabric Copilot       │
              │         │     Google BigQuery AI  ●                    │
    PROPRIETARY         │            AWS Q  ●                          │
              │         │                                              │
              │         │  ThoughtSpot  ●     ● Sigma Computing       │
              │         │                                              │
              │         │          ● AI2SQL    ● Text2SQL.ai          │
              └─────────┤                                              │
                        │─────────────────────────────────────────────│
              ┌─────────┤                                              │
              │         │  ● Wren AI (SOC2)    ● Vanna.ai 2.0        │
              │         │                                              │
    OPEN-SOURCE         │  ● Chat2DB (1M users)  ● Dataherald        │
              │         │                                              │
              │         │  ● DB-GPT       ● DBHub (MCP)              │
              │         │                                              │
              │         │  ● SQLCoder     ● DIN-SQL    ● DAIL-SQL    │
              └─────────┤                                              │
                        │            ENTERPRISE READINESS              │
                        │                   LOW                        │
                        └─────────────────────────────────────────────┘
```

---

## 2. SO SÁNH CHI TIẾT - TIER 1 (Hyperscalers)

| Tiêu chí | Snowflake Cortex | Databricks Genie | Google BigQuery AI | Microsoft Fabric | AWS Q |
|----------|-----------------|-------------------|-------------------|-----------------|-------|
| **Accuracy (claimed)** | 90-95% (verified) | High (undisclosed) | High | High | Medium-High |
| **Approach** | Semantic model + LLM | Trainable instructions | Gemini-powered | Copilot | Generative BI |
| **Multi-dialect** | Snowflake SQL | Spark SQL | BigQuery SQL | T-SQL + Fabric | Redshift SQL |
| **Governance** | Unity-level | Unity Catalog | IAM + column-level | Purview | Lake Formation |
| **Agentic** | Yes (GA 08/2025) | Agent Bricks | Emerging | Copilot-based | Emerging |
| **Pricing model** | Consumption | Consumption | Consumption | Capacity | Consumption |
| **Lock-in risk** | High (Snowflake) | High (Databricks) | High (GCP) | High (Azure) | High (AWS) |
| **Vietnamese support** | No | No | No | No | No |

**Nhận xét:** Hyperscalers cung cấp giải pháp mạnh mẽ nhưng **hoàn toàn lock-in** vào ecosystem của họ. Không vendor nào hỗ trợ Vietnamese NLQ. Chi phí tăng theo usage, không predictable.

---

## 3. SO SÁNH CHI TIẾT - OPEN-SOURCE

| Tiêu chí | Wren AI | Vanna.ai | Chat2DB | SQLCoder | DB-GPT |
|----------|---------|---------|---------|----------|--------|
| **Stars/Users** | Growing | Popular | 1M+ users | Popular | Growing |
| **Architecture** | Semantic layer + LLM | RAG-based agent | Multi-LLM support | Fine-tuned model | Agentic + SFT |
| **Semantic layer** | Built-in | Via training | Manual | No | Partial |
| **Self-hosted** | Yes | Yes | Yes | Yes | Yes |
| **Cloud option** | Yes (commercial) | Yes | Yes | No | No |
| **SOC 2** | Type 2 | No | No | No | No |
| **Vietnamese** | No | No | Partial (UI) | No | No |
| **License** | AGPL-3.0 | MIT | Apache 2.0 | Apache 2.0 | Apache 2.0 |
| **Best for** | Enterprise GenBI | Custom agents | Developer tool | Local deployment | Full AI assistant |

---

## 4. BUILD vs BUY ANALYSIS

### Option A: Mua giải pháp Hyperscaler (VD: Snowflake Cortex)

| Ưu điểm | Nhược điểm |
|---------|-----------|
| Production-ready ngay lập tức | Vendor lock-in 100% |
| 90-95% accuracy (trên verified repos) | Không hỗ trợ Vietnamese |
| Enterprise security & compliance | Chi phí consumption không predictable |
| Hỗ trợ & SLA | Không customize được cho domain banking VN |
| | Phụ thuộc vào vendor roadmap |

**Chi phí ước tính:** $50K-$200K+/năm (tùy usage)

### Option B: Adopt Open-Source (VD: Wren AI / Vanna.ai)

| Ưu điểm | Nhược điểm |
|---------|-----------|
| Miễn phí license | Cần team vận hành |
| Customizable | Accuracy phụ thuộc vào effort curation |
| Data stays on-premises | Community support only (trừ commercial tier) |
| Có thể extend cho Vietnamese | Chưa validated cho banking domain |

**Chi phí ước tính:** $100K-$200K/năm (nhân sự + infra)

### Option C: Build Custom (Khuyến nghị cho dự án này)

| Ưu điểm | Nhược điểm |
|---------|-----------|
| Full control over architecture | Thời gian phát triển 6-12 tháng |
| Optimize cho banking domain VN | Cần team có expertise |
| Data sovereignty hoàn toàn | Phải tự build & maintain |
| Vietnamese NLQ roadmap tự chủ | Higher upfront cost |
| Tận dụng code hiện có (RAG + schema) | |
| Không vendor lock-in | |

**Chi phí ước tính:** $200K-$350K (Year 1, bao gồm team) → $80K-$120K/năm (maintenance)

### Khuyến nghị: **Option C (Build Custom)** với selective adoption từ open-source

**Lý do:**
1. Domain banking VN chưa có giải pháp sẵn có → phải customize.
2. Yêu cầu data sovereignty cao (Luật AI VN, ngành tài chính).
3. Vietnamese NLQ là competitive moat - không vendor nào cung cấp.
4. Đã có foundational code (schema, RAG chunking, data generation).
5. Chi phí dài hạn thấp hơn SaaS/consumption model.

**Leverage open-source:**
- Tham khảo kiến trúc Wren AI (semantic layer approach).
- Sử dụng ChromaDB/pgvector (đã tích hợp).
- Học từ Chat2DB (product UX).
- Evaluate SQLCoder cho local model fallback.

---

## 5. VỊ THẾ CẠNH TRANH CỦA DỰ ÁN

### SWOT Analysis

| **Strengths** | **Weaknesses** |
|---------------|----------------|
| Domain expertise banking/POS | Team nhỏ, hạn chế nhân lực |
| Schema đã well-documented (14 tables) | Chưa có LLM integration |
| Data sovereignty (on-premises) | Vietnamese NLP chưa phát triển |
| Early mover tại VN market | Chưa có production experience |

| **Opportunities** | **Threats** |
|-------------------|------------|
| Greenfield market VN | Hyperscalers có thể add Vietnamese |
| Government AI investment $1B | Open-source alternatives improve fast |
| Banking digital transformation | Talent competition |
| Vietnamese NLQ = competitive moat | Regulatory changes |

---

*Nguồn: Vendor websites, GitHub repositories, Gartner, industry reports*
*Ngày cập nhật: 25/03/2026 | Phiên bản: 1.0*
