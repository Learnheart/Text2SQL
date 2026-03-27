"""Async PostgreSQL connection pool with read-only enforcement."""

from __future__ import annotations

import asyncio
import logging
import time

import asyncpg

from src.config import settings

logger = logging.getLogger(__name__)


class DatabasePool:
    """Async connection pool for query execution (read-only, with timeout)."""

    def __init__(self) -> None:
        self._pool: asyncpg.Pool | None = None

    async def init(self) -> None:
        logger.info("Initializing database pool: %s (pool: %d-%d)", settings.db_host, settings.db_min_pool, settings.db_max_pool)
        self._pool = await asyncpg.create_pool(
            dsn=settings.asyncpg_dsn,
            min_size=settings.db_min_pool,
            max_size=settings.db_max_pool,
        )
        logger.info("Database pool initialized successfully")

    async def execute(self, sql: str, timeout: int | None = None) -> dict:
        """Execute a read-only SQL query and return results.

        Returns dict with keys: columns, rows, row_count  OR  error.
        """
        if self._pool is None:
            logger.error("Database pool not initialized")
            return {"error": "Database pool not initialized"}

        timeout_s = (timeout or settings.db_statement_timeout_ms) / 1000
        start = time.perf_counter()

        try:
            async with self._pool.acquire() as conn:
                await conn.execute("SET default_transaction_read_only = on")
                await conn.execute(f"SET statement_timeout = '{settings.db_statement_timeout_ms}'")

                rows = await asyncio.wait_for(conn.fetch(sql), timeout=timeout_s)

                columns = list(rows[0].keys()) if rows else []
                data = [list(r.values()) for r in rows]
                elapsed = int((time.perf_counter() - start) * 1000)

                logger.debug("DB query: %d rows in %dms | %s", len(data), elapsed, sql[:120])

                return {
                    "columns": columns,
                    "rows": data,
                    "row_count": len(data),
                    "execution_time_ms": elapsed,
                }

        except asyncpg.exceptions.ReadOnlySQLTransactionError:
            logger.warning("Read-only violation: %s", sql[:120])
            return {"error": "Only SELECT queries are allowed (read-only connection)"}
        except TimeoutError:
            logger.error("Query timeout after %ss: %s", timeout_s, sql[:120])
            return {"error": f"Query timed out after {timeout_s}s"}
        except Exception as e:
            logger.error("DB execution error: %s | SQL: %s", e, sql[:120])
            return {"error": str(e)}

    async def close(self) -> None:
        if self._pool:
            await self._pool.close()
            self._pool = None
            logger.info("Database pool closed")
