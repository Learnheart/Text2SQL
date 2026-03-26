"""Redis cache for query results, sessions, and embeddings.

TTLs:
- Query results: 5 minutes
- Sessions: 30 minutes
- Embeddings: 1 hour
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from src.config import settings

logger = logging.getLogger(__name__)


class RedisCache:
    """Redis-backed cache for the pipeline."""

    def __init__(self) -> None:
        self._client: Any = None

    async def init(self) -> None:
        try:
            import redis.asyncio as aioredis
            self._client = aioredis.from_url(
                settings.redis_url,
                decode_responses=True,
            )
            # Test connection
            await self._client.ping()
            logger.info("Redis cache connected: %s", settings.redis_url)
        except Exception as e:
            logger.warning("Redis not available, caching disabled: %s", e)
            self._client = None

    @property
    def available(self) -> bool:
        return self._client is not None

    async def get_query(self, question: str) -> dict[str, Any] | None:
        """Look up cached query result by question hash."""
        if not self._client:
            return None

        key = self._query_key(question)
        try:
            data = await self._client.get(key)
            if data:
                logger.debug("Cache HIT: %s", question[:60])
                return json.loads(data)
        except Exception as e:
            logger.warning("Cache read error: %s", e)
        return None

    async def set_query(self, question: str, result: dict[str, Any]) -> None:
        """Cache a query result with TTL."""
        if not self._client:
            return

        key = self._query_key(question)
        try:
            await self._client.setex(key, settings.cache_query_ttl, json.dumps(result, default=str))
            logger.debug("Cache SET: %s (TTL=%ds)", question[:60], settings.cache_query_ttl)
        except Exception as e:
            logger.warning("Cache write error: %s", e)

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        """Get session data."""
        if not self._client:
            return None

        try:
            data = await self._client.get(f"session:{session_id}")
            return json.loads(data) if data else None
        except Exception:
            return None

    async def set_session(self, session_id: str, data: dict[str, Any]) -> None:
        """Store session data with TTL."""
        if not self._client:
            return

        try:
            await self._client.setex(
                f"session:{session_id}",
                settings.cache_session_ttl,
                json.dumps(data, default=str),
            )
        except Exception:
            pass

    async def close(self) -> None:
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("Redis cache closed")

    @staticmethod
    def _query_key(question: str) -> str:
        """Generate a cache key from question text."""
        normalized = question.strip().lower()
        hash_val = hashlib.sha256(normalized.encode()).hexdigest()[:16]
        return f"query:{hash_val}"
