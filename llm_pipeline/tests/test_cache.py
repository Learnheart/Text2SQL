"""Tests for Redis cache — unit tests with mocked Redis."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.cache.redis_cache import RedisCache


class TestRedisCacheKeyGeneration:
    def test_same_question_same_key(self):
        key1 = RedisCache._query_key("Tổng doanh thu?")
        key2 = RedisCache._query_key("Tổng doanh thu?")
        assert key1 == key2

    def test_case_insensitive(self):
        key1 = RedisCache._query_key("Total Revenue")
        key2 = RedisCache._query_key("total revenue")
        assert key1 == key2

    def test_strips_whitespace(self):
        key1 = RedisCache._query_key("  Tổng doanh thu?  ")
        key2 = RedisCache._query_key("Tổng doanh thu?")
        assert key1 == key2

    def test_different_questions_different_keys(self):
        key1 = RedisCache._query_key("Tổng doanh thu?")
        key2 = RedisCache._query_key("Số giao dịch?")
        assert key1 != key2

    def test_key_format(self):
        key = RedisCache._query_key("test")
        assert key.startswith("query:")


class TestRedisCacheAvailability:
    def test_not_available_before_init(self):
        cache = RedisCache()
        assert cache.available is False

    @pytest.mark.asyncio
    async def test_get_returns_none_when_unavailable(self):
        cache = RedisCache()
        result = await cache.get_query("test")
        assert result is None

    @pytest.mark.asyncio
    async def test_set_noop_when_unavailable(self):
        cache = RedisCache()
        # Should not raise
        await cache.set_query("test", {"status": "success"})
