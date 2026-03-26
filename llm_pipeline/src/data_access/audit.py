"""Audit logger — logs every query execution for Banking compliance."""

from __future__ import annotations

import asyncpg

from src.config import settings
from src.models.schemas import AuditRecord


class AuditLogger:
    """Async audit logger that writes to query_audit_logs table."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        self._pool = await asyncpg.create_pool(
            dsn=settings.asyncpg_dsn,
            min_size=1,
            max_size=2,
        )

    async def log(self, record: AuditRecord) -> None:
        if self._pool is None:
            return

        try:
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO query_audit_logs
                        (question, generated_sql, row_count, status, error_message,
                         latency_ms, attempts, tokens_used, model_used)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    """,
                    record.question,
                    record.generated_sql,
                    record.row_count,
                    record.status,
                    record.error_message,
                    record.latency_ms,
                    record.attempts,
                    record.tokens_used,
                    record.model_used,
                )
        except Exception:
            pass

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
