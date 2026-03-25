# STRATEGIC ROADMAP: Text-to-SQL Agent Platform
### Lộ trình Triển khai Cấp cao: R&D → POC → Production | Q1/2026

---

## TỔNG QUAN LỘ TRÌNH

```
═══════════════════════════════════════════════════════════════════════════════
  PHASE 1: R&D           PHASE 2: POC             PHASE 3: PRODUCTION
  (8-12 tuần)            (10-14 tuần)             (16-24 tuần)
  Q2/2026                Q3/2026                  Q4/2026 - Q1/2027
═══════════════════════════════════════════════════════════════════════════════
  ▸ Technology eval      ▸ MVP development        ▸ Hardening & scaling
  ▸ Benchmark testing    ▸ User acceptance test    ▸ Enterprise integration
  ▸ Architecture design  ▸ Accuracy validation     ▸ Monitoring & ops
  ▸ Team formation       ▸ Stakeholder demo        ▸ Change management
═══════════════════════════════════════════════════════════════════════════════
  Budget: ~$50K          Budget: ~$100K           Budget: ~$150K
  Team: 2-3 FTE          Team: 3-4 FTE            Team: 4-5 FTE
  Risk: LOW              Risk: MEDIUM             Risk: MEDIUM-HIGH
═══════════════════════════════════════════════════════════════════════════════
       ↓ GO/NO-GO              ↓ GO/NO-GO               ↓ GO-LIVE
       GATE #1                 GATE #2                   GATE #3
```

---

## PHASE 1: RESEARCH & DISCOVERY (8-12 TUẦN)

### Mục tiêu
Validate tính khả thi kỹ thuật và xác định kiến trúc tối ưu cho domain banking/POS.

### Timeline Chi tiết

```
Tuần 1-2    ┃ Kickoff & Team Formation
            ┃ ├── Phê duyệt ngân sách Phase 1
            ┃ ├── Recruit/assign core team (2-3 người)
            ┃ ├── Setup development environment
            ┃ └── Define evaluation criteria & success metrics
            ┃
Tuần 3-4    ┃ Technology Evaluation
            ┃ ├── Benchmark LLM models (Claude, GPT-4, DeepSeek, Qwen)
            ┃ │   trên schema banking hiện có (14 tables)
            ┃ ├── Evaluate RAG strategies: simple chunking vs semantic layer
            ┃ ├── Test Vector DB options: ChromaDB vs Qdrant vs pgvector
            ┃ └── Evaluate embedding models cho Vietnamese support
            ┃
Tuần 5-6    ┃ Prototype & Benchmark Testing
            ┃ ├── Build end-to-end prototype: NL → SQL → Result
            ┃ ├── Test trên 20+ business queries có sẵn (query.json)
            ┃ ├── Measure accuracy, latency, cost per query
            ┃ └── Identify failure patterns & edge cases
            ┃
Tuần 7-8    ┃ Architecture Decision Records (ADRs)
            ┃ ├── Finalize technology stack selection
            ┃ ├── Design target architecture (agentic vs single-shot)
            ┃ ├── Define security model (read-only, metadata-only)
            ┃ └── Document trade-offs & rationale
            ┃
Tuần 9-10   ┃ Semantic Layer Design
            ┃ ├── Enrich schema.json với business glossary
            ┃ ├── Define metric definitions (doanh thu, lợi nhuận, etc.)
            ┃ ├── Create column-level descriptions & sample values
            ┃ └── Test semantic layer impact trên accuracy
            ┃
Tuần 11-12  ┃ Phase 1 Wrap-up & Go/No-Go
            ┃ ├── Compile evaluation report
            ┃ ├── Present findings to Steering Committee
            ┃ ├── GO/NO-GO decision based on criteria
            ┃ └── Plan Phase 2 if approved
```

### Deliverables Phase 1
| # | Deliverable | Mô tả |
|---|------------|--------|
| D1.1 | Technology Evaluation Report | So sánh LLMs, Vector DBs, Embedding models |
| D1.2 | Prototype Demo | End-to-end NL → SQL → Result working demo |
| D1.3 | Accuracy Benchmark Report | Accuracy/latency/cost trên 20+ queries |
| D1.4 | Architecture Decision Records | Stack selection + rationale |
| D1.5 | Enriched Semantic Layer | Schema.json + business glossary + metrics |

### GO/NO-GO Gate #1 - Tiêu chí

| Tiêu chí | Ngưỡng | Phương pháp đo |
|----------|--------|-----------------|
| SQL accuracy (simple queries) | ≥ 85% | Test trên 20 simple queries |
| SQL accuracy (complex queries) | ≥ 60% | Test trên 10 complex queries (CTEs, joins) |
| Average latency | ≤ 10 giây | End-to-end response time |
| Cost per query | ≤ $0.05 | LLM API + infra cost |
| Security validation | Pass | No data leakage trong prototype |

---

## PHASE 2: PROOF OF CONCEPT (10-14 TUẦN)

### Mục tiêu
Xây dựng MVP có thể demo cho stakeholders, validate với real users, và đạt accuracy production-grade.

### Timeline Chi tiết

```
Tuần 1-3    ┃ MVP Core Development
            ┃ ├── Implement agentic pipeline:
            ┃ │   Router → Schema Linker → SQL Generator → Validator
            ┃ ├── Build self-correction loop (retry on SQL errors)
            ┃ ├── Implement query execution engine (read-only)
            ┃ └── Setup logging & monitoring baseline
            ┃
Tuần 4-5    ┃ Semantic Layer & RAG Enhancement
            ┃ ├── Integrate enriched semantic layer từ Phase 1
            ┃ ├── Implement hybrid retrieval (vector + keyword)
            ┃ ├── Add few-shot example selection (query history)
            ┃ └── Build feedback loop: user corrections → improve retrieval
            ┃
Tuần 6-7    ┃ UI & User Experience
            ┃ ├── Build chat interface (web-based)
            ┃ ├── Add query explanation feature
            ┃ ├── Implement result visualization (tables, basic charts)
            ┃ └── Add query history & favorites
            ┃
Tuần 8-9    ┃ User Acceptance Testing (UAT)
            ┃ ├── Onboard 5-10 pilot users (data analysts, business users)
            ┃ ├── Collect feedback (accuracy, usability, trust)
            ┃ ├── Track failure cases, build regression test suite
            ┃ └── Iterate on UX based on feedback
            ┃
Tuần 10-11  ┃ Accuracy Optimization
            ┃ ├── Analyze failure patterns từ UAT
            ┃ ├── Expand training examples cho weak areas
            ┃ ├── Fine-tune prompt templates
            ┃ └── A/B test: single-shot vs agentic pipeline
            ┃
Tuần 12-14  ┃ Stakeholder Demo & Go/No-Go
            ┃ ├── Prepare demo scenario cho C-Level
            ┃ ├── Compile POC evaluation report
            ┃ ├── Present ROI case (time saved, queries automated)
            ┃ ├── GO/NO-GO decision
            ┃ └── Plan Phase 3 if approved
```

### Deliverables Phase 2
| # | Deliverable | Mô tả |
|---|------------|--------|
| D2.1 | Working MVP | Agentic Text-to-SQL với chat UI |
| D2.2 | UAT Report | User feedback, accuracy metrics, failure analysis |
| D2.3 | Regression Test Suite | 50+ test cases covering known patterns |
| D2.4 | C-Level Demo Package | Live demo + slide deck + ROI analysis |
| D2.5 | Production Readiness Assessment | Gap analysis for Phase 3 |

### GO/NO-GO Gate #2 - Tiêu chí

| Tiêu chí | Ngưỡng | Phương pháp đo |
|----------|--------|-----------------|
| SQL accuracy (top 50 business queries) | ≥ 85% | Test suite automated |
| User satisfaction (NPS) | ≥ 7/10 | Pilot user survey |
| Average latency (end-to-end) | ≤ 8 giây | Production-like environment |
| Uptime during UAT | ≥ 95% | Monitoring logs |
| Security audit | Pass | Penetration test on read-only layer |
| Business case ROI | Positive within 18 months | Financial model |

---

## PHASE 3: PRODUCTION DEPLOYMENT (16-24 TUẦN)

### Mục tiêu
Đưa hệ thống lên production, đảm bảo reliability, scalability, và organizational adoption.

### Timeline Chi tiết

```
Tuần 1-4    ┃ Production Hardening
            ┃ ├── Infrastructure setup (Kubernetes/Docker Compose)
            ┃ ├── Implement authentication & authorization (SSO/LDAP)
            ┃ ├── Setup rate limiting & query governance
            ┃ ├── Implement audit logging (ai_sử_dụng_nào, query_gì, kết_quả)
            ┃ └── Configure backup & disaster recovery
            ┃
Tuần 5-8    ┃ Enterprise Integration
            ┃ ├── Connect to production databases (read-only replicas)
            ┃ ├── Integrate with existing BI tools (if applicable)
            ┃ ├── Setup data refresh pipeline cho Vector DB
            ┃ ├── Implement multi-database support
            ┃ └── API gateway for programmatic access
            ┃
Tuần 9-12   ┃ Monitoring, Observability & Ops
            ┃ ├── Setup monitoring dashboard (query volume, accuracy, latency)
            ┃ ├── Implement alerting (accuracy drops, latency spikes)
            ┃ ├── Build feedback collection pipeline
            ┃ ├── Setup model performance tracking (drift detection)
            ┃ └── Create runbooks for common issues
            ┃
Tuần 13-16  ┃ Change Management & Rollout
            ┃ ├── Training program cho end users
            ┃ ├── Create user documentation & FAQ
            ┃ ├── Phased rollout: Team A → Department → Organization
            ┃ ├── Designate internal champions
            ┃ └── Establish feedback & continuous improvement process
            ┃
Tuần 17-20  ┃ Scale & Optimize
            ┃ ├── Onboard additional databases/schemas
            ┃ ├── Optimize cost (caching, query deduplication)
            ┃ ├── Implement Vietnamese NLQ (Phase 2 of language support)
            ┃ ├── Add advanced features: scheduled reports, alerts
            ┃ └── Performance tuning based on production metrics
            ┃
Tuần 21-24  ┃ Stabilization & Handover
            ┃ ├── Knowledge transfer to operations team
            ┃ ├── Finalize SLA definitions
            ┃ ├── Complete compliance documentation
            ┃ ├── Post-launch review & lessons learned
            ┃ └── Plan future roadmap (Vietnamese NLQ, more domains)
```

### Deliverables Phase 3
| # | Deliverable | Mô tả |
|---|------------|--------|
| D3.1 | Production System | Live Text-to-SQL platform |
| D3.2 | Operations Runbook | Monitoring, alerting, incident response |
| D3.3 | User Training Materials | Guides, videos, FAQ |
| D3.4 | Compliance Documentation | Tuân thủ Luật AI VN + data governance |
| D3.5 | Post-Launch Review | Metrics, lessons learned, future roadmap |

### GO-LIVE Gate #3 - Tiêu chí

| Tiêu chí | Ngưỡng |
|----------|--------|
| SQL accuracy (production queries) | ≥ 85% |
| System availability | ≥ 99.5% |
| Average response time | ≤ 5 giây |
| Security audit | Pass (external auditor) |
| Compliance review | Pass (Legal/Compliance team) |
| User training completion | ≥ 80% target users |
| Runbook & documentation | Complete |

---

## TỔNG HỢP NGÂN SÁCH & NGUỒN LỰC

### Ngân sách theo Phase

| Phase | Duration | Team | Budget | Cumulative |
|-------|----------|------|--------|------------|
| Phase 1: R&D | 8-12 tuần | 2-3 FTE | ~$50K | $50K |
| Phase 2: POC | 10-14 tuần | 3-4 FTE | ~$100K | $150K |
| Phase 3: Production | 16-24 tuần | 4-5 FTE | ~$150K | **$300K** |
| **Tổng** | **34-50 tuần** | **Max 5 FTE** | **~$300K** | |

### Team Structure Evolution

```
Phase 1 (2-3 FTE):              Phase 2 (3-4 FTE):           Phase 3 (4-5 FTE):
├── ML/AI Engineer (lead)       ├── ML/AI Engineer (lead)    ├── ML/AI Engineer (lead)
├── Data Engineer                ├── Data Engineer            ├── Data Engineer
└── Backend Dev (part-time)     ├── Backend Developer        ├── Backend Developer
                                └── UX/Frontend Dev          ├── DevOps/SRE
                                                             └── UX/Frontend Dev
```

---

## RISK REGISTER (TOP 5)

| # | Rủi ro | Xác suất | Tác động | Mitigation |
|---|--------|----------|----------|------------|
| R1 | Accuracy không đạt 85% trên production data | Trung bình | Cao | Đầu tư semantic layer; human-in-the-loop; gate criteria rõ ràng |
| R2 | Vietnamese NLQ performance thấp (~4-6%) | Cao | Trung bình | English-first strategy; phát triển VN sau khi validate English |
| R3 | LLM API cost vượt ngân sách | Trung bình | Trung bình | Caching, query dedup, local model fallback |
| R4 | Data security incident | Thấp | Rất cao | Read-only access, metadata-only processing, audit logging |
| R5 | User adoption thấp | Trung bình | Cao | Change management, internal champions, phased rollout |

---

## KEY SUCCESS FACTORS

1. **Semantic Layer Quality**: Đầu tư vào metadata curation là yếu tố quyết định accuracy (#1 lesson từ Snowflake).
2. **Incremental Approach**: Go/No-Go gates ở mỗi phase để kiểm soát rủi ro đầu tư.
3. **User-Centric**: Involve pilot users từ Phase 2; build trust dần dần.
4. **Security-First**: Read-only, metadata-only, audit logging từ ngày đầu.
5. **Executive Sponsorship**: CIO/CTO champion để đảm bảo organizational support.

---

## VISUAL ROADMAP

```
2026 Q2          2026 Q3          2026 Q4          2027 Q1
Apr May Jun      Jul Aug Sep      Oct Nov Dec      Jan Feb Mar
═══════════      ═══════════      ═══════════      ═══════════
█████████████    ░░░░░░░░░░░░░    ░░░░░░░░░░░░░    ░░░░░░░░░░░
PHASE 1: R&D     ░░░░░░░░░░░░░    ░░░░░░░░░░░░░    ░░░░░░░░░░░
  ↓ Gate #1      ░░░░░░░░░░░░░    ░░░░░░░░░░░░░    ░░░░░░░░░░░
░░░░░░░░░░░░░    █████████████    ████░░░░░░░░░    ░░░░░░░░░░░
                 PHASE 2: POC     ░░░░░░░░░░░░░    ░░░░░░░░░░░
                   ↓ Gate #2      ░░░░░░░░░░░░░    ░░░░░░░░░░░
░░░░░░░░░░░░░    ░░░░░░░░░░░░░    ████████████████████████████
                                  PHASE 3: PRODUCTION
                                                    ↓ GO-LIVE
                                                    ★ Launch
```

---

*Tài liệu được chuẩn bị theo chuẩn tư vấn chiến lược Big4.*
*Ngày tạo: 25/03/2026 | Phiên bản: 1.0*
