# Market Landscape: AI Agents cho Dữ liệu Có Cấu trúc
### Phân tích Thị trường & Xu hướng | Q1/2026

---

## 1. TỔNG QUAN QUY MÔ THỊ TRƯỜNG

Text-to-SQL nằm tại giao điểm của nhiều phân khúc thị trường đang tăng trưởng mạnh:

| Phân khúc | Quy mô 2025 | Dự phóng | CAGR |
|-----------|-------------|----------|------|
| Global AI Market | ~$375.93B | $2,480B (2034) | 26.6% |
| AI Software Market | $174.1B | Tăng trưởng đến 2030 | 25% |
| **AI Agents Market** | **$7.8 - $15B** | **$52 - $100B (2030)** | **46.3%** |
| Conversational AI | $19.21B | $132.86B (2034) | 24.0% |
| Analytics Platforms | $48.6B | Tăng trưởng | 15.5% |
| Data Science & AI Platforms | -- | Tăng 38.6% trong 2024 | -- |

### Dự báo chính từ Gartner:
- **40% ứng dụng doanh nghiệp** sẽ tích hợp AI Agents vào cuối 2026 (từ <5% năm 2025).
- Agentic AI có thể chiếm **~30% doanh thu Enterprise Application Software** vào 2035 (~$450B+).

---

## 2. CÁC NHÓM NGƯỜI CHƠI CHÍNH

### 2.1 Tier 1: Hyperscalers & Platform Vendors

| Vendor | Sản phẩm | Điểm mạnh | Hạn chế |
|--------|----------|-----------|---------|
| **Snowflake** | Cortex Analyst / Intelligence | Tuyên bố 90-95% accuracy trên verified repos; GA agentic AI framework (08/2025) | Đòi hỏi semantic model curation nặng |
| **Databricks** | AI/BI Genie / Agent Bricks | NL-to-SQL với trainable instructions; Unity Catalog tích hợp | Ecosystem lock-in |
| **Google Cloud** | BigQuery AI (Gemini) | Tăng trưởng 350% usage trong 9 tháng; 60%+ code acceptance | Phụ thuộc GCP |
| **Microsoft** | Fabric Copilot / SSMS Copilot | GA tại Ignite 2025; tích hợp SQL Server 2025 | Giới hạn trong Microsoft ecosystem |
| **AWS** | Amazon Q in QuickSight/Redshift | Generative BI; NL-driven visual creation | Muộn hơn so với Snowflake/Databricks |

### 2.2 Tier 2: BI-Native NLQ Players

| Vendor | Điểm nổi bật |
|--------|-------------|
| **ThoughtSpot** | Tiên phong search-driven analytics; Spotter AI cho live NL querying |
| **Sigma Computing** | Gartner MQ 2025; Snowflake Partner of the Year 2025 |
| **Tableau/Salesforce** | Tăng market share +6pp từ 2023; AI-augmented analytics |
| **Hex** | Tăng gấp đôi BI spend share từ 2023; notebook-style + AI |

### 2.3 Tier 3: Open-Source & Specialized

| Dự án | Mô tả | Nổi bật |
|-------|--------|---------|
| **SQLCoder** (Defog.ai) | Model 15B fine-tuned (StarCoder base) | Vượt GPT-3.5-turbo trên sql-eval; deploy local |
| **DIN-SQL** | Decomposed In-Context Learning | Multi-stage prompting cho schema linking, joins |
| **DAIL-SQL** | Prompt engineering framework | 86.6% EX trên Spider |
| **Wren AI** | Open-source GenBI với semantic layer | SOC 2 Type 2; commercial cloud option |
| **Vanna.ai** | Personalized SQL agent | Vanna 2.0 (cuối 2025) - production-ready agent |
| **Chat2DB** | Tool Text-to-SQL phổ biến nhất GitHub | 1M+ users; Apache 2.0; hỗ trợ 10+ LLMs |
| **DB-GPT** | Agentic AI data assistant | SFT trên LLMs; sandboxed execution |
| **DBHub** | Universal database MCP server | 100K+ downloads; kết nối AI → DB qua MCP |
| **Dataherald** | NL-to-SQL engine cho enterprise | Fine-tuning + business context injection |

---

## 3. PHÂN TÍCH XU HƯỚNG CHÍNH

### 3.1 Convergence: Text-to-SQL đang bị hấp thụ vào BI Platforms
- Mọi BI vendor lớn đều đang ship NLQ capabilities.
- Standalone text-to-SQL tools trở nên niche (developer-focused) hoặc trở thành target M&A.
- MCP (Model Context Protocol) tạo paradigm mới: bất kỳ AI assistant nào cũng có thể query database.

### 3.2 Semantic Layer trở thành yêu cầu bắt buộc
- Snowflake đạt 90-95% accuracy nhờ **semantic model curation** - không phải nhờ LLM giỏi hơn.
- Wren AI, AtScale áp dụng semantic-layer-first architecture.
- Xu hướng: accuracy phụ thuộc metadata quality nhiều hơn model capability.

### 3.3 Agentic Architecture thay thế Single-shot Generation
- Multi-agent systems (MARS-SQL): agents chuyên biệt + RL cho verification.
- Self-correction loops với execution feedback.
- Human-in-the-loop validation cho enterprise accuracy.

### 3.4 Security & Governance là gatekeeper chính
- Zero-Knowledge Schema Inference Attacks (NAACL 2025) cho thấy Text-to-SQL có thể leak schema info.
- Metadata-only processing (không expose raw data cho LLM) trở thành security standard.
- EU AI Act và Luật AI Việt Nam đặt compliance requirements mới.

---

## 4. ENTERPRISE ADOPTION - CÁC CON SỐ THỰC TẾ

| Metric | Giá trị | Nguồn |
|--------|---------|-------|
| SQL adoption rate trong IT | 75.5% | Industry surveys |
| Doanh nghiệp triển khai NLP (2025) | 72% | Market research |
| Accuracy trên Spider benchmark | ~91% | Academic SOTA |
| Accuracy trên Spider 2.0 (enterprise-realistic) | **~36%** | ICLR 2025 |
| Accuracy trên LiveSQLBench (contamination-free) | **~45%** | arXiv 2025 |
| Accuracy Snowflake trên verified repos | 90-95% | Snowflake blog |
| Tăng tốc phân tích (sau triển khai NLQ) | **10x faster** | Enterprise case studies |
| Giảm analyst bottleneck | **60%** | Enterprise case studies |

### Gap quan trọng: Academic vs Production
- **Spider 1.0 (academic): ~91%** → "solved" cho mục đích nghiên cứu.
- **Spider 2.0 (enterprise): ~36%** → phản ánh độ phức tạp thực tế (3000+ columns, multi-dialect).
- **LiveSQLBench: ~45%** → benchmark đầu tiên chống data contamination.
- **MultiSpider 2.0 (non-English): ~4-6%** → multilingual performance gap rất lớn.

**Kết luận:** Accuracy production-grade đòi hỏi đầu tư nghiêm túc vào metadata curation, semantic layer, và domain-specific tuning - không thể chỉ dựa vào out-of-the-box LLM.

---

## 5. ĐỀ XUẤT CHO DỰ ÁN TEXT2SQL

### Positioning Strategy
Dựa trên phân tích thị trường, dự án nên định vị là **Domain-Specific Text-to-SQL Agent** cho ngành banking/fintech tại Việt Nam, với các lợi thế:

1. **Niche market chưa bị chiếm**: Chưa có giải pháp Text-to-SQL chuyên biệt cho banking Việt Nam.
2. **Regulatory advantage**: Tuân thủ Luật AI Việt Nam từ đầu; data sovereignty.
3. **Semantic layer curation**: Schema banking/POS đã có sẵn (14 tables, well-documented).
4. **Build vs Buy**: Build nội bộ phù hợp hơn do yêu cầu data sovereignty và domain-specific accuracy.

---

*Nguồn: Gartner, IMARC, Fortune Business Insights, Snowflake, Databricks, Spider benchmark, VLDB 2025, ACM Computing Surveys*
*Ngày cập nhật: 25/03/2026 | Phiên bản: 1.0*
