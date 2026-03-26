-- init_db.sql — Additional setup for Text-to-SQL Agent Platform
-- Run AFTER gen_data.py has created the business schema and seeded data.

-- 1. Enable pgvector extension (for future Phase 2 migration)
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Query audit log table (compliance requirement for Banking domain)
CREATE TABLE IF NOT EXISTS query_audit_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    generated_sql TEXT,
    row_count INTEGER,
    status TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    latency_ms INTEGER,
    tool_calls_count INTEGER DEFAULT 0,
    tokens_used INTEGER DEFAULT 0,
    model_used TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON query_audit_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_logs_status ON query_audit_logs(status);

-- 3. User corrections table (for feedback loop / example store)
CREATE TABLE IF NOT EXISTS user_corrections (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    question TEXT NOT NULL,
    wrong_sql TEXT,
    correct_sql TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- 4. Read-only role for agent SQL execution
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'text2sql_readonly') THEN
        CREATE ROLE text2sql_readonly;
    END IF;
END
$$;

GRANT CONNECT ON DATABASE test_db TO text2sql_readonly;
GRANT USAGE ON SCHEMA public TO text2sql_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO text2sql_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO text2sql_readonly;
