"""
Redis cache layer for NSE API responses.
Falls back to in-memory dict if Redis is unavailable (dev mode).
"""

import json
import asyncio
from typing import Optional, Any
from datetime import datetime

try:
    import redis.asyncio as aioredis
    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False


class Cache:
    """
    Unified cache with Redis primary + in-memory fallback.
    All TTLs in seconds.
    """
    DEFAULT_TTLS = {
        "option_chain": 5,      # Refresh every 5s during market hours
        "indices": 3,
        "ban_list": 86400,      # Daily
        "fii_dii": 21600,       # 6 hours
        "iv_history": 3600,     # 1 hour
        "scan_result": 60,      # 1 minute
    }

    def __init__(self, redis_url: str = "redis://localhost:6379"):
        self._redis: Optional[Any] = None
        self._memory: dict = {}
        self._memory_ttl: dict = {}
        self._redis_url = redis_url

    async def connect(self):
        if not REDIS_AVAILABLE:
            print("Redis not installed — using in-memory cache (not suitable for production)")
            return
        try:
            self._redis = aioredis.from_url(self._redis_url, decode_responses=True)
            await self._redis.ping()
            print("Redis connected")
        except Exception as e:
            print(f"Redis unavailable ({e}) — falling back to in-memory cache")
            self._redis = None

    async def get(self, key: str) -> Optional[Any]:
        if self._redis:
            try:
                val = await self._redis.get(key)
                return json.loads(val) if val else None
            except Exception:
                # Fallback to memory on Redis error
                pass
        # In-memory fallback with TTL check
        if key in self._memory:
            expires_at = self._memory_ttl.get(key, 0)
            if datetime.now().timestamp() < expires_at:
                return self._memory[key]
            else:
                # Clean up expired entry
                self._memory.pop(key, None)
                self._memory_ttl.pop(key, None)
        return None

    async def set(self, key: str, value: Any, ttl: int = 60):
        serialized = json.dumps(value, default=str)
        if self._redis:
            try:
                await self._redis.setex(key, ttl, serialized)
                return
            except Exception:
                # Fallback to memory on Redis error
                pass
        self._memory[key] = value
        self._memory_ttl[key] = datetime.now().timestamp() + ttl

    async def delete(self, key: str):
        if self._redis:
            try:
                await self._redis.delete(key)
            except Exception:
                pass
        self._memory.pop(key, None)
        self._memory_ttl.pop(key, None)

    def cache_key(self, prefix: str, *args) -> str:
        return f"fo_scanner:{prefix}:{':'.join(str(a) for a in args)}"

    async def close(self):
        """Close Redis connection if open."""
        if self._redis:
            try:
                await self._redis.close()
            except Exception:
                pass
            self._redis = None


# Singleton instance
cache = Cache()
