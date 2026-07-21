"""
Unified Cache System - Production-Ready Query Result Caching
============================================================

Features:
- Redis backend with intelligent in-memory fallback (LRU)
- Tag-based cache invalidation
- Safe JSON-only serialization for DataFrames and plain values (no pickle)
- Auto-caching decorator
- Cache statistics and monitoring integration
- Async support for non-blocking operations

Author: Manufacturing Analytics Team
Date: 2025-11-24
"""

import asyncio
import functools
import hashlib
import json
import logging
import os
from collections import OrderedDict
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

# Type markers for the JSON cache envelope
_CACHE_TYPE_DATAFRAME = "df"
_CACHE_TYPE_JSON = "json"


def _serialize_cache_value(value: Any) -> Optional[bytes]:
    """Serialize a cache value to bytes using safe JSON encoding.

    DataFrames are stored as JSON with orient='split' for type fidelity.
    Plain JSON-native types (dict, list, str, int, float, bool, None) are
    stored directly. Returns None for non-serializable types.

    Args:
        value: The value to serialize.

    Returns:
        UTF-8 encoded JSON bytes, or None if the value cannot be serialized.
    """
    if isinstance(value, pd.DataFrame):
        envelope = {
            "_t": _CACHE_TYPE_DATAFRAME,
            "_d": value.to_json(orient="split", date_format="iso"),
        }
    elif isinstance(value, (dict, list, str, int, float, bool, type(None))):
        envelope = {"_t": _CACHE_TYPE_JSON, "_d": value}
    else:
        return None
    return json.dumps(envelope).encode("utf-8")


def _deserialize_cache_value(data: bytes) -> Any:
    """Deserialize a cache value from bytes using safe JSON decoding.

    Recognises the envelope format written by _serialize_cache_value.
    Falls back to plain JSON parsing for legacy data that was stored
    before the envelope format was introduced.

    Args:
        data: Raw bytes from Redis.

    Returns:
        The deserialized Python object (DataFrame, dict, list, etc.).

    Raises:
        ValueError: If the data cannot be decoded.
    """
    raw = json.loads(data.decode("utf-8"))
    if isinstance(raw, dict) and "_t" in raw:
        if raw["_t"] == _CACHE_TYPE_DATAFRAME:
            return pd.read_json(StringIO(raw["_d"]), orient="split")
        return raw["_d"]
    # Legacy plain-JSON data (no envelope)
    return raw


logger = logging.getLogger(__name__)

# Try to import Redis
try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️  Redis not installed. Install with: pip install redis")


class LRUCache:
    """
    Thread-safe LRU (Least Recently Used) cache for in-memory fallback.

    Features:
    - Automatic eviction of least recently used items
    - TTL support
    - Memory size tracking
    - Thread-safe operations
    """

    def __init__(self, max_items: int = 1000, max_memory_mb: int = 512):
        """
        Initialize LRU cache.

        Args:
            max_items: Maximum number of cached items
            max_memory_mb: Maximum memory usage in MB
        """
        self.max_items = max_items
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.cache: OrderedDict = OrderedDict()
        self.lock = asyncio.Lock()

    async def get(self, key: str) -> Optional[Any]:
        """Get value from cache, moving it to end (most recently used)."""
        async with self.lock:
            if key not in self.cache:
                return None

            value, expiry = self.cache[key]

            # Check if expired
            if datetime.now() > expiry:
                del self.cache[key]
                return None

            # Move to end (most recently used)
            self.cache.move_to_end(key)
            return value

    async def set(self, key: str, value: Any, ttl: int):
        """Set value in cache with TTL."""
        async with self.lock:
            expiry = datetime.now() + timedelta(seconds=ttl)

            # If key exists, update it
            if key in self.cache:
                self.cache[key] = (value, expiry)
                self.cache.move_to_end(key)
            else:
                # Add new item
                self.cache[key] = (value, expiry)

                # Evict LRU item if over limit
                if len(self.cache) > self.max_items:
                    self.cache.popitem(last=False)  # Remove oldest (first) item

    async def delete(self, key: str):
        """Delete key from cache."""
        async with self.lock:
            if key in self.cache:
                del self.cache[key]

    async def clear(self) -> int:
        """Clear all items from cache."""
        async with self.lock:
            count = len(self.cache)
            self.cache.clear()
            return count

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        async with self.lock:
            return {
                "total_items": len(self.cache),
                "max_items": self.max_items,
                "max_memory_mb": self.max_memory_bytes / (1024 * 1024),
            }


class UnifiedCacheClient:
    """
    Unified cache client with Redis backend and LRU in-memory fallback.

    Consolidates all caching logic into one place.
    """

    def __init__(
        self,
        redis_host: str = "localhost",
        redis_port: int = 6379,
        redis_db: int = 0,
        default_ttl: int = 3600,
        max_memory_mb: int = 512,
    ):
        """
        Initialize unified cache client.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            default_ttl: Default TTL in seconds (1 hour)
            max_memory_mb: Max memory for fallback cache
        """
        self.default_ttl = default_ttl
        self.redis_client: Optional[redis.Redis] = None
        self.use_redis = False

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
            "errors": 0,
        }

        # Try Redis connection
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=False,
                    socket_connect_timeout=5,
                    socket_keepalive=True,
                    health_check_interval=30,
                )
                # Test connection
                self.redis_client.ping()
                self.use_redis = True
                logger.info(
                    f"✅ Cache: Connected to Redis at {redis_host}:{redis_port}"
                )
            except Exception as e:
                logger.warning(f"⚠️  Cache: Redis connection failed: {e}")
                self.use_redis = False

        # Fallback: LRU in-memory cache
        if not self.use_redis:
            self.memory_cache = LRUCache(max_items=1000, max_memory_mb=max_memory_mb)
            logger.info("✅ Cache: Using LRU in-memory fallback")

    def generate_cache_key(
        self, query: str, params: Optional[Dict] = None, prefix: str = "cache:query:"
    ) -> str:
        """
        Generate cache key from query and parameters.

        Args:
            query: SQL query or identifier
            params: Additional parameters
            prefix: Key prefix

        Returns:
            str: Cache key
        """
        content = query.strip().lower()
        if params:
            content += json.dumps(params, sort_keys=True)
        key_hash = hashlib.sha256(content.encode()).hexdigest()
        return f"{prefix}{key_hash}"

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache.

        Args:
            key: Cache key

        Returns:
            Cached value or None
        """
        try:
            if self.use_redis:
                data = await asyncio.to_thread(self.redis_client.get, key)
                if data:
                    self.stats["hits"] += 1
                    logger.debug(f"Cache HIT: {key[:40]}...")
                    return _deserialize_cache_value(data)
                else:
                    self.stats["misses"] += 1
                    logger.debug(f"Cache MISS: {key[:40]}...")
                    return None
            else:
                value = await self.memory_cache.get(key)
                if value is not None:
                    self.stats["hits"] += 1
                    logger.debug(f"Cache HIT: {key[:40]}...")
                else:
                    self.stats["misses"] += 1
                    logger.debug(f"Cache MISS: {key[:40]}...")
                return value
        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats["errors"] += 1
            self.stats["misses"] += 1
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
        tags: Optional[List[str]] = None,
    ) -> bool:
        """
        Set value in cache.

        Args:
            key: Cache key
            value: Value to cache
            ttl: TTL in seconds (None = default)
            tags: Tags for invalidation

        Returns:
            bool: Success status
        """
        ttl = ttl or self.default_ttl

        try:
            if self.use_redis:
                data = _serialize_cache_value(value)
                if data is None:
                    logger.warning(
                        "Skipping non-serializable cache value: %s",
                        type(value).__name__,
                    )
                    return False

                await asyncio.to_thread(self.redis_client.setex, key, ttl, data)

                # Store tags for invalidation
                if tags:
                    for tag in tags:
                        tag_key = f"cache:tag:{tag}"
                        await asyncio.to_thread(self.redis_client.sadd, tag_key, key)
                        await asyncio.to_thread(self.redis_client.expire, tag_key, ttl)

                self.stats["sets"] += 1
                logger.debug(f"Cached: {key[:40]}... (TTL: {ttl}s)")
                return True
            else:
                await self.memory_cache.set(key, value, ttl)
                self.stats["sets"] += 1
                logger.debug(f"Cached: {key[:40]}... (TTL: {ttl}s)")
                return True
        except Exception as e:
            logger.error(f"Cache set error: {e}")
            self.stats["errors"] += 1
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache."""
        try:
            if self.use_redis:
                await asyncio.to_thread(self.redis_client.delete, key)
            else:
                await self.memory_cache.delete(key)

            self.stats["deletes"] += 1
            return True
        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            self.stats["errors"] += 1
            return False

    async def clear_all(self) -> int:
        """Clear all cache entries."""
        try:
            if self.use_redis:
                keys = await asyncio.to_thread(self.redis_client.keys, "cache:*")
                if keys:
                    count = await asyncio.to_thread(self.redis_client.delete, *keys)
                    logger.info(f"Cleared {count} Redis cache entries")
                    return count
                return 0
            else:
                count = await self.memory_cache.clear()
                logger.info(f"Cleared {count} memory cache entries")
                return count
        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return 0

    async def invalidate_by_tag(self, tag: str) -> int:
        """Invalidate all cache entries with a specific tag."""
        try:
            if not self.use_redis:
                logger.warning("Tag-based invalidation only supported with Redis")
                return 0

            tag_key = f"cache:tag:{tag}"
            cache_keys = await asyncio.to_thread(self.redis_client.smembers, tag_key)

            if cache_keys:
                # Decode byte strings
                cache_keys = [
                    k.decode("utf-8") if isinstance(k, bytes) else k for k in cache_keys
                ]
                count = await asyncio.to_thread(self.redis_client.delete, *cache_keys)
                await asyncio.to_thread(self.redis_client.delete, tag_key)
                logger.info(f"Invalidated {count} cache entries with tag '{tag}'")
                return count
            return 0
        except Exception as e:
            logger.error(f"Cache invalidate error: {e}")
            return 0

    async def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total_requests if total_requests > 0 else 0

        result = {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate_percent": round(hit_rate * 100, 2),
            "backend": "redis" if self.use_redis else "memory_lru",
            "redis_available": self.use_redis,
        }

        if self.use_redis and self.redis_client:
            try:
                info = await asyncio.to_thread(self.redis_client.info, "memory")
                result["memory_used_mb"] = round(
                    info.get("used_memory", 0) / (1024 * 1024), 2
                )
                result["memory_peak_mb"] = round(
                    info.get("used_memory_peak", 0) / (1024 * 1024), 2
                )

                # Count cache keys
                cache_keys = await asyncio.to_thread(
                    self.redis_client.keys, "cache:query:*"
                )
                result["cached_queries"] = len(cache_keys)
            except (AttributeError, Exception) as e:
                logger.debug(f"Failed to get Redis cache stats: {e}")
                # Continue without Redis stats
        else:
            memory_stats = await self.memory_cache.get_stats()
            result.update(memory_stats)

        return result


# Global cache instance
_cache_client: Optional[UnifiedCacheClient] = None


def get_cache_client() -> UnifiedCacheClient:
    """
    Get global cache client instance.

    Returns:
        UnifiedCacheClient: Global cache instance
    """
    global _cache_client
    if _cache_client is None:
        _cache_client = UnifiedCacheClient(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            default_ttl=int(os.getenv("CACHE_TTL", "3600")),
        )
    return _cache_client


def cached(
    ttl: int = 3600, tags: Optional[List[str]] = None, key_prefix: str = "cache:query:"
):
    """
    Decorator for automatic caching of function results.

    Usage:
        @cached(ttl=1800, tags=["MASTER_SHOT_TABLE"])
        def fetch_data(equipment_code, start_date, end_date):
            # ... expensive Snowflake query ...
            return dataframe

    Args:
        ttl: Time to live in seconds
        tags: Tags for cache invalidation
        key_prefix: Cache key prefix

    Returns:
        Decorated function with automatic caching
    """

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def async_wrapper(*args, **kwargs):
            cache = get_cache_client()

            # Generate cache key from function name + args
            key_parts = [func.__module__, func.__name__]
            key_parts.extend(str(arg) for arg in args)
            key_parts.extend(f"{k}={v}" for k, v in sorted(kwargs.items()))
            cache_key = cache.generate_cache_key(":".join(key_parts), prefix=key_prefix)

            # Try to get from cache
            cached_value = await cache.get(cache_key)
            if cached_value is not None:
                logger.info(f"✅ Cache HIT for {func.__name__}")
                return cached_value

            # Cache miss - execute function
            logger.info(f"⚠️  Cache MISS for {func.__name__} - executing...")
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = await asyncio.to_thread(func, *args, **kwargs)

            # Store in cache
            await cache.set(cache_key, result, ttl=ttl, tags=tags)

            return result

        @functools.wraps(func)
        def sync_wrapper(*args, **kwargs):
            # For sync functions, run in event loop
            return asyncio.run(async_wrapper(*args, **kwargs))

        return async_wrapper if asyncio.iscoroutinefunction(func) else sync_wrapper

    return decorator
