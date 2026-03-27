# /test — Run unit tests and/or e2e tests

## Arguments

$ARGUMENTS — format: `[mode] [phase]`

- **mode**: `unit` (default), `e2e`, `all`
- **phase**: `phase1` (rag_single_agent), `phase2` (llm_pipeline), hoặc bỏ trống = cả hai

Examples:
- `/test` — unit test cả 2 phases
- `/test unit` — unit test cả 2 phases
- `/test unit phase2` — unit test chỉ llm_pipeline
- `/test e2e` — e2e test cả 2 phases (cần Docker)
- `/test e2e phase2` — e2e test chỉ llm_pipeline
- `/test all` — unit + e2e cả 2 phases

---

## Instructions

Parse arguments từ `$ARGUMENTS` để xác định `mode` và `phase`. Nếu rỗng, default là `unit` cho cả 2 phases.

### Step 1: Xác định scope

Từ arguments, xác định:
- `mode`: `unit`, `e2e`, hoặc `all`
- `phases`: danh sách phases cần chạy

Phase mapping:
- `phase1` → `rag_single_agent/`
- `phase2` → `llm_pipeline/`
- Không chỉ định → cả hai

### Step 2: Chạy Unit Tests (nếu mode = unit hoặc all)

Chạy unit test **song song** cho các phases được chọn:

```bash
# Phase 1
cd /c/Projects/Text2SQL/rag_single_agent && python -m pytest tests/ -m "not e2e" -v --tb=short 2>&1

# Phase 2
cd /c/Projects/Text2SQL/llm_pipeline && python -m pytest tests/ -m "not e2e" -v --tb=short 2>&1
```

Chạy 2 lệnh trên song song (parallel Bash calls) nếu cả 2 phases được chọn.

### Step 3: Chạy E2E Tests (nếu mode = e2e hoặc all)

#### 3a. Kiểm tra Docker infrastructure

```bash
docker ps --filter "name=pipeline_postgres" --filter "status=running" --format "{{.Names}}"
docker ps --filter "name=pipeline_redis" --filter "status=running" --format "{{.Names}}"
```

Nếu containers chưa chạy:

```bash
cd /c/Projects/Text2SQL/llm_pipeline/docker && docker compose up -d
```

Chờ healthy:
```bash
docker compose -f /c/Projects/Text2SQL/llm_pipeline/docker/docker-compose.yml ps
```

#### 3b. Khởi tạo database và seed data

Kiểm tra xem DB đã có data chưa:
```bash
PGPASSWORD=test_db_password psql -h localhost -U test_db_user -d test_db -c "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE';" 2>/dev/null
```

Nếu chưa có tables hoặc cần reset, chạy tuần tự:
```bash
# Init schema + extensions
PGPASSWORD=test_db_password psql -h localhost -U test_db_user -d test_db -f /c/Projects/Text2SQL/llm_pipeline/scripts/init_db.sql

# Seed test data
PGPASSWORD=test_db_password psql -h localhost -U test_db_user -d test_db -f /c/Projects/Text2SQL/llm_pipeline/scripts/seed_test_data.sql
```

#### 3c. Chạy e2e tests

```bash
# Phase 1
cd /c/Projects/Text2SQL/rag_single_agent && python -m pytest tests/ -m e2e -v --tb=short 2>&1

# Phase 2
cd /c/Projects/Text2SQL/llm_pipeline && python -m pytest tests/ -m e2e -v --tb=short 2>&1
```

Chạy tuần tự vì cùng chia sẻ PostgreSQL trên port 5432.

### Step 4: Báo cáo kết quả

Sau khi chạy xong, trình bày kết quả theo format:

```
## Test Results

### Unit Tests
| Phase | Passed | Failed | Skipped | Time |
|-------|--------|--------|---------|------|
| Phase 1 (rag_single_agent) | X | Y | Z | Ns |
| Phase 2 (llm_pipeline) | X | Y | Z | Ns |

### E2E Tests (nếu chạy)
| Phase | Passed | Failed | Skipped | Time |
|-------|--------|--------|---------|------|
| Phase 1 (rag_single_agent) | X | Y | Z | Ns |
| Phase 2 (llm_pipeline) | X | Y | Z | Ns |

### Failures (nếu có)
- `test_name` — error message tóm tắt
```

Nếu có test FAIL, phân tích ngắn gọn nguyên nhân và đề xuất fix.

### Lưu ý quan trọng

- **KHÔNG tự động fix code** khi test fail — chỉ báo cáo và đề xuất
- **KHÔNG commit** kết quả test
- Nếu Docker không available cho e2e → báo rõ cho user và hướng dẫn setup
- Nếu `.env` thiếu config → báo rõ biến nào cần set
