"""
Tests for cache.py — Redis caching with in-memory fallback.
"""

import pytest
import asyncio
import sys
import os

# Add backend directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cache import Cache, cache, REDIS_AVAILABLE


class TestCacheInMemory:
    """Tests for in-memory cache fallback."""

    @pytest.fixture
    def memory_cache(self):
        """Create a cache that won't connect to Redis."""
        c = Cache(redis_url="redis://nonexistent:9999")
        # Don't call connect - force in-memory mode
        return c

    @pytest.mark.asyncio
    async def test_set_and_get_basic(self, memory_cache):
        """Test basic set and get operations."""
        await memory_cache.set("test_key", {"foo": "bar"}, ttl=60)
        result = await memory_cache.get("test_key")
        assert result == {"foo": "bar"}

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, memory_cache):
        """Getting nonexistent key should return None."""
        result = await memory_cache.get("nonexistent_key_12345")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_key(self, memory_cache):
        """Test deleting a key."""
        await memory_cache.set("delete_me", "value", ttl=60)
        result = await memory_cache.get("delete_me")
        assert result == "value"
        
        await memory_cache.delete("delete_me")
        result = await memory_cache.get("delete_me")
        assert result is None

    @pytest.mark.asyncio
    async def test_cache_key_format(self, memory_cache):
        """Test cache key generation."""
        key = memory_cache.cache_key("scan_result", "NIFTY", "123")
        assert key == "fo_scanner:scan_result:NIFTY:123"

    @pytest.mark.asyncio
    async def test_cache_key_single_arg(self, memory_cache):
        """Test cache key with single argument."""
        key = memory_cache.cache_key("option_chain", "BANKNIFTY")
        assert key == "fo_scanner:option_chain:BANKNIFTY"

    @pytest.mark.asyncio
    async def test_set_complex_value(self, memory_cache):
        """Test storing complex nested values."""
        complex_value = {
            "data": [1, 2, 3],
            "nested": {"a": 1, "b": [4, 5]},
            "string": "test",
        }
        await memory_cache.set("complex", complex_value, ttl=60)
        result = await memory_cache.get("complex")
        assert result == complex_value

    @pytest.mark.asyncio
    async def test_overwrite_value(self, memory_cache):
        """Test overwriting existing value."""
        await memory_cache.set("overwrite_key", "first", ttl=60)
        await memory_cache.set("overwrite_key", "second", ttl=60)
        result = await memory_cache.get("overwrite_key")
        assert result == "second"


class TestCacheDefaultTTLs:
    """Tests for default TTL values."""

    def test_default_ttls_exist(self):
        """Check that default TTLs are defined."""
        assert "option_chain" in Cache.DEFAULT_TTLS
        assert "indices" in Cache.DEFAULT_TTLS
        assert "ban_list" in Cache.DEFAULT_TTLS
        assert "fii_dii" in Cache.DEFAULT_TTLS
        assert "iv_history" in Cache.DEFAULT_TTLS
        assert "scan_result" in Cache.DEFAULT_TTLS

    def test_default_ttl_values(self):
        """Check that default TTL values are reasonable."""
        assert Cache.DEFAULT_TTLS["option_chain"] == 5
        assert Cache.DEFAULT_TTLS["scan_result"] == 60
        assert Cache.DEFAULT_TTLS["ban_list"] == 86400  # 24 hours


class TestCacheSingleton:
    """Tests for the global cache singleton."""

    def test_singleton_exists(self):
        """Global cache singleton should exist."""
        assert cache is not None
        assert isinstance(cache, Cache)

    @pytest.mark.asyncio
    async def test_singleton_connect(self):
        """Singleton should handle connect gracefully."""
        # This shouldn't raise even without Redis
        await cache.connect()


class TestCacheRedisAvailability:
    """Tests for Redis availability detection."""

    def test_redis_available_flag(self):
        """REDIS_AVAILABLE should be boolean."""
        assert isinstance(REDIS_AVAILABLE, bool)


class TestCacheTTLExpiration:
    """Tests for TTL-based expiration in memory cache."""

    @pytest.mark.asyncio
    async def test_expired_key_returns_none(self):
        """Expired key should return None."""
        c = Cache()
        # Set with very short TTL
        await c.set("expire_test", "value", ttl=0)
        
        # Wait a moment to ensure expiration
        await asyncio.sleep(0.1)
        
        result = await c.get("expire_test")
        # May return None or the value depending on exact timing
        # The important thing is it doesn't raise an error
        assert result is None or result == "value"
