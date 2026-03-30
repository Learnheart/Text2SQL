# STRATEGIC BRIEF: Text-to-SQL Agent Platform (BIRD Benchmark)
### Báo cáo Tóm tắt Chiến lược cho C-Level | Tháng 03/2026

---

## 1. VẤN ĐỀ KINH DOANH

**Thực trạng:**
- 80% nhu cầu phân tích dữ liệu trong doanh nghiệp phụ thuộc vào đội ngũ Data Analyst/Engineer biết viết SQL.
- Thời gian trung bình từ lúc business đặt câu hỏi đến khi nhận được insight: **2-5 ngày làm việc**.
- SQL có tỷ lệ adoption 75.5% trong ngành IT, nhưng chỉ ~15% nhân sự business có thể tự viết truy vấn.
- Bottleneck data team khiến **60% yêu cầu phân tích bị trì hoãn** hoặc không được thực hiện.

**Cơ hội:**
Triển khai AI Agent có khả năng chuyển đổi câu hỏi ngôn ngữ tự nhiên thành truy vấn SQL chính xác, cho phép bất kỳ nhân sự nào trong tổ chức tự phân tích dữ liệu mà không cần kỹ năng SQL.

---

## 2. THỊ TRƯỜNG & XU HƯỚNG

| Chỉ số | Giá trị |
|---------|---------|
| Quy mô thị trường AI Agents (2025) | $7.8 - $15B |
| Dự phóng 2030 | $52 - $100B |
| CAGR | **46.3%** |
| Dự báo Gartner: Enterprise apps có AI Agent (2026) | **40%** (từ <5% năm 2025) |
| Doanh thu AI agentic trong Enterprise Software đến 2035 | ~$450B+ |

**Đặc biệt tại Việt Nam:**
- Thị trường Enterprise AI: $161M (2025) → **$1.83B (2034)**, CAGR 31%.
- Xếp hạng **#6 toàn cầu** về WIN World AI Index 2025.
- Luật Trí tuệ Nhân tạo có hiệu lực **01/03/2026** với ngân sách chính phủ $1B cho AI.

---

## 3. GIẢI PHÁP ĐỀ XUẤT

Xây dựng **Text-to-SQL Agent Platform** theo kiến trúc RAG (Retrieval-Augmented Generation), đánh giá trên **BIRD-SQL benchmark** (70+ databases, 9,430+ examples):

```
Người dùng → Câu hỏi (NL) + db_id
       ↓
[Schema Retrieval] → Lấy metadata bảng/cột liên quan từ Vector DB (per db_id)
       ↓
[LLM Agent] → Sinh SQL query chính xác + giải thích
       ↓
[SQL Execution] → Thực thi trên SQLite database (read-only, per db_id)
       ↓
[Evaluation] → So sánh kết quả với BIRD ground truth (execution accuracy)
```

**Lợi thế cạnh tranh so với mua giải pháp thương mại:**
- **Kiểm soát dữ liệu**: Dữ liệu không rời khỏi hạ tầng nội bộ.
- **Tùy biến domain**: Tối ưu cho schema và nghiệp vụ riêng (bất kỳ domain nào).
- **Benchmark-driven**: Đánh giá accuracy trên BIRD standard benchmark trước khi deploy production.
- **Chi phí dài hạn**: Tránh vendor lock-in; chi phí vận hành thấp hơn SaaS 40-60% sau năm thứ 2.
- **Compliance**: Tuân thủ Luật AI Việt Nam và các quy định bảo mật dữ liệu.

---

## 4. ĐÁNH GIÁ KHẢ THI

| Tiêu chí | Đánh giá | Chi tiết |
|-----------|----------|----------|
| **Kỹ thuật** | Khả thi cao | SOTA accuracy trên BIRD benchmark: ~70-80%. Kiến trúc RAG + Agent đã được validate bởi Snowflake, Databricks |
| **Thị trường** | Timing tốt | Giai đoạn early-majority adoption; Việt Nam đang đầu tư mạnh vào AI |
| **Nguồn lực** | Cần đầu tư | Team 3-5 người (ML Engineer, Data Engineer, Backend Dev); 6-9 tháng cho MVP |
| **Rủi ro chính** | Trung bình | Enterprise accuracy (~36% trên Spider 2.0) đòi hỏi curation metadata cẩn thận; hallucination risk |
| **Compliance** | Quản lý được | Kiến trúc metadata-only không expose raw data cho LLM |

---

## 5. DỰ PHÓNG TÀI CHÍNH SƠ BỘ

### Chi phí đầu tư (Year 1)

| Hạng mục | Ước tính |
|----------|----------|
| Nhân sự (3-5 FTE x 12 tháng) | $150K - $250K |
| Hạ tầng Cloud/GPU | $30K - $60K |
| LLM API costs (Claude/GPT) | $12K - $36K |
| Công cụ & license | $5K - $15K |
| **Tổng Year 1** | **$197K - $361K** |

### Lợi ích dự kiến

| Lợi ích | Ước tính hàng năm |
|---------|-------------------|
| Giảm thời gian phân tích (10x faster) | Tiết kiệm 2,000+ giờ analyst/năm |
| Tự phục vụ cho 100+ business users | Tương đương 2-3 FTE analyst |
| Giảm backlog data requests 60% | Quyết định kinh doanh nhanh hơn |
| **Payback period ước tính** | **12-18 tháng** |

---

## 6. KHUYẾN NGHỊ HÀNH ĐỘNG

### Khuyến nghị: **TIẾN HÀNH** - Bắt đầu từ Phase 1 (R&D) với scope kiểm soát

**Bước tiếp theo ngay lập tức:**

| # | Hành động | Timeline | Owner |
|---|-----------|----------|-------|
| 1 | Phê duyệt ngân sách Phase 1 (R&D): ~$50K | Tuần 1-2 | CFO/CIO |
| 2 | Thành lập core team (2-3 người) | Tuần 2-4 | CTO/VP Eng |
| 3 | Hoàn thành POC + BIRD benchmark evaluation | Tuần 5-16 | Tech Lead |
| 4 | Demo & đánh giá Go/No-Go cho Phase 2 | Tuần 17-18 | Steering Committee |

**Decision gate:** Sau Phase 1 POC, đánh giá execution accuracy ≥ 70% trên BIRD test set trước khi commit Phase 2 (migrate sang production database).

---

*Tài liệu được chuẩn bị theo chuẩn tư vấn chiến lược Big4.*
*Ngày tạo: 25/03/2026 | Phiên bản: 1.0*
