-- Initialize database for LLM Pipeline (Phase 2)
-- Run: psql -U test_db_user -d test_db -f scripts/init_db.sql

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Schema embeddings table
CREATE TABLE IF NOT EXISTS schema_embeddings (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(1024)  -- bge-m3 dimension
);

-- Example embeddings table
CREATE TABLE IF NOT EXISTS example_embeddings (
    id TEXT PRIMARY KEY,
    document TEXT NOT NULL,
    metadata JSONB DEFAULT '{}',
    embedding vector(1024)
);

-- HNSW indexes for fast similarity search
CREATE INDEX IF NOT EXISTS idx_schema_embeddings_hnsw
ON schema_embeddings USING hnsw (embedding vector_cosine_ops);

CREATE INDEX IF NOT EXISTS idx_example_embeddings_hnsw
ON example_embeddings USING hnsw (embedding vector_cosine_ops);

-- Audit log table (extended for Phase 2)
CREATE TABLE IF NOT EXISTS query_audit_logs (
    id SERIAL PRIMARY KEY,
    question TEXT NOT NULL,
    generated_sql TEXT,
    row_count INTEGER,
    status VARCHAR(50) DEFAULT 'pending',
    error_message TEXT,
    latency_ms INTEGER DEFAULT 0,
    attempts INTEGER DEFAULT 1,
    tokens_used INTEGER DEFAULT 0,
    model_used VARCHAR(100) DEFAULT '',
    created_at TIMESTAMP DEFAULT NOW()
);

-- Create read-only role for query execution
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'readonly_user') THEN
        CREATE ROLE readonly_user LOGIN PASSWORD 'readonly_password';
    END IF;
END $$;

-- Grant read-only access
-- Grant connect on current database (dynamic to avoid hardcoded db name)
DO $$ BEGIN EXECUTE format('GRANT CONNECT ON DATABASE %I TO readonly_user', current_database()); END $$;
GRANT USAGE ON SCHEMA public TO readonly_user;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readonly_user;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO readonly_user;

-- Index on audit logs for querying
CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON query_audit_logs (created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON query_audit_logs (status);
