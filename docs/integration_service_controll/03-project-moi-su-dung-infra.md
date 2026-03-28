# Hướng dẫn project mới sử dụng infrastructure của Service Controller

> Hướng dẫn tạo project mới từ đầu, tận dụng toàn bộ shared infrastructure có sẵn.

---

## 1. Tổng quan

Service Controller cung cấp sẵn các infrastructure services sau. Project mới chỉ cần kết nối và sử dụng, không cần tự cài đặt hay cấu hình bất kỳ service nào.

| Service | Mô tả | Kết nối (trong Docker) | Kết nối (từ host) |
|---------|-------|------------------------|-------------------|
| PostgreSQL + pgvector | Relational DB, hỗ trợ vector | `infra-postgres:5432` | `localhost:5432` |
| Redis | Cache, message queue | `infra-redis:6379` | `localhost:6379` |
| MinIO | Object storage (S3-compatible) | `infra-minio:9000` | `localhost:9000` |
| Milvus | Vector database | `infra-milvus:19530` | `localhost:19530` |
| Elasticsearch | Full-text search | `infra-elasticsearch:9200` | `localhost:9200` |
| Langfuse | LLM observability | `infra-langfuse:3000` | `localhost:3001` |
| Grafana | Monitoring dashboard | — | `localhost:3000` |
| Prometheus | Metrics | — | `localhost:9090` |

---

## 2. Tạo project mới — Quick Start

### Bước 1: Tạo thư mục project

```bash
mkdir C:\Projects\MyNewProject
cd C:\Projects\MyNewProject
```

### Bước 2: Đăng ký với Service Controller

```bash
sc project add C:\Projects\MyNewProject --name my_new_project
```

Output:

```
Registered project: my_new_project
  Path: C:\Projects\MyNewProject
  Namespaces:
    postgres: my_new_project_db
    redis: 3
    minio: my_new_project-bucket
    milvus: my_new_project_
    elasticsearch: my_new_project_
  Port range: 8030-8039
```

**Ghi nhớ các giá trị này** — đây là namespace riêng của project, đảm bảo data không lẫn với project khác.

### Bước 3: Tạo file .env

```bash
sc project env my_new_project --output C:\Projects\MyNewProject\.env
```

### Bước 4: Tạo docker-compose.yml

```yaml
# C:\Projects\MyNewProject\docker-compose.yml
services:
  app:
    build: .
    container_name: my-new-project-app
    ports:
      - "8030:8000"                   # Port từ allocated range
    env_file: .env
    deploy:
      resources:
        limits:
          memory: 2048M
          cpus: "1.0"
        reservations:
          memory: 256M
          cpus: "0.25"
    networks:
      - infra-net

networks:
  infra-net:
    external: true                    # Join vào shared infra network
```

### Bước 5: Tạo Dockerfile

```dockerfile
# C:\Projects\MyNewProject\Dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Bước 6: Khởi động

```bash
# Tự động khởi động shared infra (nếu chưa chạy) và project
sc project up my_new_project
```

---

## 3. Sử dụng từng service cụ thể

### 3.1 PostgreSQL + pgvector

**Đặc điểm:**
- Image: `pgvector/pgvector:0.8.1-pg18-trixie` (PostgreSQL 18 + pgvector 0.8.1)
- Extension `vector` đã được enable sẵn trong database của project
- Connection limit: 40 connections/database
- Credentials: `postgres:postgres` (dev environment)

**Connection string:**

```
DATABASE_URL=postgresql://postgres:postgres@infra-postgres:5432/my_new_project_db
```

**Python (SQLAlchemy):**

```python
import os
from sqlalchemy import create_engine

engine = create_engine(
    os.getenv("DATABASE_URL"),
    pool_size=15,         # Số connections giữ sẵn
    max_overflow=10,      # Thêm tối đa 10 khi busy → tổng max 25
    pool_timeout=30,      # Chờ 30s nếu pool hết
    pool_recycle=1800,    # Recycle connection sau 30 phút
)
```

**Sử dụng pgvector:**

```python
from sqlalchemy import text

# Tạo bảng với vector column
with engine.connect() as conn:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS documents (
            id SERIAL PRIMARY KEY,
            content TEXT,
            embedding vector(1536)
        )
    """))
    conn.commit()

# Tìm kiếm vector
with engine.connect() as conn:
    results = conn.execute(text("""
        SELECT id, content, embedding <=> :query_vec AS distance
        FROM documents
        ORDER BY distance
        LIMIT 10
    """), {"query_vec": str(embedding_list)})
```

**Alembic migration:**

```python
# alembic/env.py
import os
config.set_main_option("sqlalchemy.url", os.getenv("DATABASE_URL"))
```

```bash
# Chạy migration (trong container hoặc từ host)
alembic upgrade head
```

### 3.2 Redis

**Đặc điểm:**
- Mỗi project được cấp 1 DB number riêng (0-15)
- `maxmemory`: 768MB, policy: `allkeys-lru`
- `maxclients`: 300 (chia sẻ giữa các project)
- Hỗ trợ: caching, pub/sub, task queue, session store

**Connection string:**

```
REDIS_URL=redis://infra-redis:6379/3
```

**Python (redis-py):**

```python
import os
import redis

# Cách 1: Từ URL
r = redis.from_url(os.getenv("REDIS_URL"))

# Cách 2: Connection pool
pool = redis.ConnectionPool.from_url(
    os.getenv("REDIS_URL"),
    max_connections=30,
)
r = redis.Redis(connection_pool=pool)

# Sử dụng
r.set("my_key", "value", ex=3600)  # TTL 1 giờ
value = r.get("my_key")
```

**Làm task queue với Celery:**

```python
# celery_config.py
import os

broker_url = os.getenv("REDIS_URL")
result_backend = os.getenv("REDIS_URL")
```

**Lưu ý:**
- Dữ liệu Redis là volatile (có thể bị xóa khi đầy memory do LRU policy)
- Không lưu data quan trọng trong Redis mà không có fallback
- Prefix key với project name để dễ debug: `my_project:user:123`

### 3.3 Milvus (Vector Database)

**Đặc điểm:**
- Sử dụng collection prefix để phân biệt data giữa các project
- Hỗ trợ: ANN search, hybrid search, filtering
- RAM limit: 4GB

**Environment variables:**

```
MILVUS_HOST=infra-milvus
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=my_new_project_
```

**Python (pymilvus):**

```python
import os
from pymilvus import connections, Collection, FieldSchema, CollectionSchema, DataType

# Kết nối
connections.connect(
    alias="default",
    host=os.getenv("MILVUS_HOST"),
    port=os.getenv("MILVUS_PORT"),
)

# Tạo collection với prefix
prefix = os.getenv("MILVUS_COLLECTION_PREFIX")
collection_name = f"{prefix}documents"    # → my_new_project_documents

fields = [
    FieldSchema(name="id", dtype=DataType.INT64, is_primary=True, auto_id=True),
    FieldSchema(name="text", dtype=DataType.VARCHAR, max_length=65535),
    FieldSchema(name="embedding", dtype=DataType.FLOAT_VECTOR, dim=1536),
]
schema = CollectionSchema(fields, description="Document embeddings")
collection = Collection(name=collection_name, schema=schema)

# Tạo index
collection.create_index(
    field_name="embedding",
    index_params={"index_type": "IVF_FLAT", "metric_type": "COSINE", "params": {"nlist": 128}},
)

# Search
collection.load()
results = collection.search(
    data=[query_embedding],
    anns_field="embedding",
    param={"metric_type": "COSINE", "params": {"nprobe": 16}},
    limit=10,
    output_fields=["text"],
)
```

**Quy tắc đặt tên collection:**
- Luôn dùng prefix: `{MILVUS_COLLECTION_PREFIX}{tên_collection}`
- Ví dụ: `my_new_project_documents`, `my_new_project_chunks`, `my_new_project_qa_pairs`

### 3.4 Elasticsearch

**Đặc điểm:**
- Single-node, security disabled (dev environment)
- JVM heap: 2GB
- Sử dụng index prefix để phân biệt data

**Environment variables:**

```
ELASTICSEARCH_URL=http://infra-elasticsearch:9200
ELASTICSEARCH_INDEX_PREFIX=my_new_project_
```

**Python (elasticsearch-py):**

```python
import os
from elasticsearch import Elasticsearch

es = Elasticsearch(os.getenv("ELASTICSEARCH_URL"))
prefix = os.getenv("ELASTICSEARCH_INDEX_PREFIX")

# Tạo index với prefix
index_name = f"{prefix}documents"    # → my_new_project_documents
es.indices.create(
    index=index_name,
    body={
        "settings": {"number_of_shards": 1, "number_of_replicas": 0},
        "mappings": {
            "properties": {
                "title": {"type": "text", "analyzer": "standard"},
                "content": {"type": "text"},
                "created_at": {"type": "date"},
            }
        }
    },
    ignore=400,  # Bỏ qua nếu đã tồn tại
)

# Index document
es.index(index=index_name, body={"title": "Hello", "content": "World"})

# Search
results = es.search(
    index=index_name,
    body={"query": {"match": {"content": "World"}}},
)
```

**Quy tắc đặt tên index:**
- Luôn dùng prefix: `{ELASTICSEARCH_INDEX_PREFIX}{tên_index}`
- Ví dụ: `my_new_project_documents`, `my_new_project_logs`

### 3.5 MinIO (Object Storage)

**Đặc điểm:**
- S3-compatible API
- Mỗi project 1 bucket riêng
- Console: http://localhost:9001 (minioadmin/minioadmin)

**Environment variables:**

```
MINIO_ENDPOINT=infra-minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=my_new_project-bucket
```

**Python (minio):**

```python
import os
from minio import Minio

client = Minio(
    os.getenv("MINIO_ENDPOINT"),
    access_key=os.getenv("MINIO_ACCESS_KEY"),
    secret_key=os.getenv("MINIO_SECRET_KEY"),
    secure=False,
)

bucket = os.getenv("MINIO_BUCKET")

# Tạo bucket (nếu chưa có)
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)

# Upload file
client.fput_object(bucket, "data/file.pdf", "/local/path/file.pdf")

# Download file
client.fget_object(bucket, "data/file.pdf", "/local/download/file.pdf")

# Tạo presigned URL (7 ngày)
from datetime import timedelta
url = client.presigned_get_object(bucket, "data/file.pdf", expires=timedelta(days=7))
```

**Python (boto3 — S3-compatible):**

```python
import os
import boto3

s3 = boto3.client(
    "s3",
    endpoint_url=f"http://{os.getenv('MINIO_ENDPOINT')}",
    aws_access_key_id=os.getenv("MINIO_ACCESS_KEY"),
    aws_secret_access_key=os.getenv("MINIO_SECRET_KEY"),
)

bucket = os.getenv("MINIO_BUCKET")
s3.upload_file("/local/file.pdf", bucket, "data/file.pdf")
```

### 3.6 Langfuse (LLM Observability)

**Đặc điểm:**
- UI: http://localhost:3001
- Theo dõi LLM calls, costs, latency
- Không có isolation per project — dùng chung 1 instance

**Python:**

```python
from langfuse import Langfuse

langfuse = Langfuse(
    public_key="pk-...",        # Lấy từ Langfuse UI
    secret_key="sk-...",
    host="http://infra-langfuse:3000",  # Trong Docker
    # host="http://localhost:3001",     # Từ host
)

# Trace LLM call
trace = langfuse.trace(name="my-rag-pipeline")
generation = trace.generation(
    name="openai-call",
    model="gpt-4",
    input=[{"role": "user", "content": "Hello"}],
    output="Hi there!",
)
langfuse.flush()
```

---

## 4. Template project đầy đủ

### 4.1 Cấu trúc thư mục khuyến nghị

```
MyNewProject/
├── docker-compose.yml          # Chỉ app, không có infra
├── Dockerfile
├── .env                        # Auto-generated bởi sc
├── .env.example                # Template cho developer khác
├── requirements.txt
├── alembic/                    # Database migrations
│   ├── alembic.ini
│   └── versions/
├── src/
│   ├── main.py                 # FastAPI entry point
│   ├── config.py               # Đọc env variables
│   ├── database.py             # PostgreSQL connection
│   ├── cache.py                # Redis connection
│   ├── storage.py              # MinIO connection
│   └── search.py               # Elasticsearch connection
└── tests/
```

### 4.2 Config module mẫu

```python
# src/config.py
import os
from dataclasses import dataclass


@dataclass
class Settings:
    # PostgreSQL
    database_url: str = os.getenv("DATABASE_URL", "")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "")

    # Milvus
    milvus_host: str = os.getenv("MILVUS_HOST", "localhost")
    milvus_port: int = int(os.getenv("MILVUS_PORT", "19530"))
    milvus_prefix: str = os.getenv("MILVUS_COLLECTION_PREFIX", "")

    # Elasticsearch
    elasticsearch_url: str = os.getenv("ELASTICSEARCH_URL", "")
    elasticsearch_prefix: str = os.getenv("ELASTICSEARCH_INDEX_PREFIX", "")

    # MinIO
    minio_endpoint: str = os.getenv("MINIO_ENDPOINT", "")
    minio_access_key: str = os.getenv("MINIO_ACCESS_KEY", "")
    minio_secret_key: str = os.getenv("MINIO_SECRET_KEY", "")
    minio_bucket: str = os.getenv("MINIO_BUCKET", "")


settings = Settings()
```

### 4.3 File .env.example

Tạo file này để developer khác biết cần những env variables gì:

```env
# .env.example — Copy thành .env và điền giá trị
# Hoặc chạy: sc project env <project_name> -o .env

# PostgreSQL
DATABASE_URL=postgresql://postgres:postgres@infra-postgres:5432/<project_name>_db

# Redis
REDIS_URL=redis://infra-redis:6379/<db_number>

# Milvus
MILVUS_HOST=infra-milvus
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=<project_name>_

# Elasticsearch
ELASTICSEARCH_URL=http://infra-elasticsearch:9200
ELASTICSEARCH_INDEX_PREFIX=<project_name>_

# MinIO
MINIO_ENDPOINT=infra-minio:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=<project_name>-bucket
```

### 4.4 docker-compose.yml — Template nhiều services

```yaml
services:
  api:
    build: .
    container_name: my-project-api
    ports:
      - "8030:8000"
    env_file: .env
    command: uvicorn src.main:app --host 0.0.0.0 --port 8000
    deploy:
      resources:
        limits:
          memory: 1024M
          cpus: "0.5"
    networks:
      - infra-net

  worker:
    build: .
    container_name: my-project-worker
    env_file: .env
    command: celery -A src.tasks worker --loglevel=info
    deploy:
      resources:
        limits:
          memory: 1024M
          cpus: "0.5"
    networks:
      - infra-net

  beat:
    build: .
    container_name: my-project-beat
    env_file: .env
    command: celery -A src.tasks beat --loglevel=info
    deploy:
      resources:
        limits:
          memory: 256M
          cpus: "0.25"
    networks:
      - infra-net

networks:
  infra-net:
    external: true
```

---

## 5. Quy tắc quan trọng

### 5.1 Data Isolation

| Service | Quy tắc | Ví dụ |
|---------|---------|-------|
| PostgreSQL | Dùng đúng database name được cấp | `my_new_project_db` |
| Redis | Dùng đúng DB number được cấp | `3` (trong URL: `/3`) |
| Milvus | Collection name phải có prefix | `my_new_project_documents` |
| Elasticsearch | Index name phải có prefix | `my_new_project_logs` |
| MinIO | Chỉ dùng bucket được cấp | `my_new_project-bucket` |

**KHÔNG BAO GIỜ:**
- Truy cập database của project khác
- Dùng Redis DB number của project khác
- Tạo collection/index không có prefix
- Ghi vào bucket của project khác

### 5.2 Connection Pool Limits

PostgreSQL có giới hạn 40 connections/database. Cấu hình pool phù hợp:

| Thành phần | pool_size | max_overflow | Tổng |
|------------|-----------|--------------|------|
| API server | 15 | 10 | 25 |
| Worker | 5 | 5 | 10 |
| Migrations | — | — | 3 |
| **Tổng** | | | **38** (trong limit 40) |

### 5.3 Resource Limits

Mỗi project nên đặt resource limits trong docker-compose.yml:

```yaml
deploy:
  resources:
    limits:
      memory: 2048M     # Giới hạn cứng
      cpus: "1.0"
    reservations:
      memory: 256M      # Đảm bảo luôn có ít nhất 256MB
      cpus: "0.25"
```

### 5.4 Port Range

Dùng port trong range được cấp phát. Ví dụ range `8030-8039`:

| Port | Dùng cho |
|------|----------|
| 8030 | API server |
| 8031 | gRPC server (nếu có) |
| 8032 | WebSocket (nếu có) |
| 8033-8039 | Dự phòng |

---

## 6. Dev không Docker (tùy chọn)

Nếu muốn chạy app trực tiếp trên máy (không trong container) nhưng vẫn dùng shared infra:

```bash
# Đảm bảo infra đang chạy
sc infra up

# Tạo .env cho host (thay hostname = localhost)
sc project env my_new_project > .env.docker
```

Tạo `.env.local` với `localhost`:

```env
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/my_new_project_db
REDIS_URL=redis://localhost:6379/3
MILVUS_HOST=localhost
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=my_new_project_
ELASTICSEARCH_URL=http://localhost:9200
ELASTICSEARCH_INDEX_PREFIX=my_new_project_
MINIO_ENDPOINT=localhost:9000
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin
MINIO_BUCKET=my_new_project-bucket
```

```bash
# Chạy app
export $(cat .env.local | xargs)
uvicorn src.main:app --reload
```

---

## 7. Chuyển lên Production

Khi deploy production, chỉ cần thay đổi `.env` — code không cần sửa:

```env
# Production .env
DATABASE_URL=postgresql://user:pass@prod-postgres.example.com:5432/my_project_db
REDIS_URL=redis://:pass@prod-redis.example.com:6379/0
MILVUS_HOST=prod-milvus.example.com
MILVUS_PORT=19530
MILVUS_COLLECTION_PREFIX=my_project_
ELASTICSEARCH_URL=https://prod-es.example.com:9200
ELASTICSEARCH_INDEX_PREFIX=my_project_
MINIO_ENDPOINT=prod-s3.example.com
MINIO_ACCESS_KEY=prod_access_key
MINIO_SECRET_KEY=prod_secret_key
MINIO_BUCKET=my-project-bucket
```

Namespace logic (database name, prefix, bucket) vẫn giữ nguyên. Chỉ thay đổi connection strings.
