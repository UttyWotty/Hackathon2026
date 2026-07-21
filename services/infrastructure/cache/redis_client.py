"""
Redis Cache Client for Query Result Caching.

Features:
- Query result caching with TTL
- Redis backend with in-memory fallback
- DataFrame serialization
- Cache statistics tracking
- Automatic cleanup

Author: Utku Gulbardak
Date: 2025-10-29
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta
from io import StringIO
from typing import Any, Dict, Optional

import pandas as pd

logger = logging.getLogger(__name__)

try:
    import redis

    REDIS_AVAILABLE = True
except ImportError:
    REDIS_AVAILABLE = False
    logger.warning("⚠️  Redis not installed, using in-memory cache fallback")


class CacheClient:
    """
    Cache client with Redis backend or in-memory fallback.

    Features:
    - Query result caching with TTL
    - Automatic key generation from query text
    - DataFrame serialization/deserialization
    - Cache statistics tracking
    - Memory management
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
        Initialize cache client.

        Args:
            redis_host: Redis server host
            redis_port: Redis server port
            redis_db: Redis database number
            default_ttl: Default TTL in seconds (1 hour)
            max_memory_mb: Max memory for in-memory cache (MB)
        """
        self.default_ttl = default_ttl
        self.max_memory_mb = max_memory_mb

        # Try Redis connection
        if REDIS_AVAILABLE:
            try:
                self.redis_client = redis.Redis(
                    host=redis_host,
                    port=redis_port,
                    db=redis_db,
                    decode_responses=False,
                    socket_connect_timeout=2,
                    socket_timeout=2,
                )
                # Test connection
                self.redis_client.ping()
                self.use_redis = True
                logger.info(f"✅ Connected to Redis: {redis_host}:{redis_port}")
            except Exception as e:
                logger.warning(f"⚠️  Redis connection failed: {e}")
                self.use_redis = False
        else:
            self.use_redis = False

        # Fallback: in-memory cache
        if not self.use_redis:
            self._memory_cache: Dict[str, tuple] = {}  # key -> (value, expiry)
            logger.info("Using in-memory cache fallback")

        # Statistics
        self.stats = {
            "hits": 0,
            "misses": 0,
            "sets": 0,
            "deletes": 0,
        }

    def _generate_key(self, query: str, params: Optional[Dict] = None) -> str:
        """
        Generate cache key from query and parameters.

        Args:
            query: SQL query text
            params: Query parameters

        Returns:
            str: Cache key (hash)
        """
        # Normalize query (strip whitespace, lowercase)
        normalized = query.strip().lower()

        # Include params in key if provided
        if params:
            normalized += json.dumps(params, sort_keys=True)

        # Generate SHA256 hash
        key_hash = hashlib.sha256(normalized.encode()).hexdigest()
        return f"query_cache:{key_hash}"

    def get(self, query: str, params: Optional[Dict] = None) -> Optional[pd.DataFrame]:
        """
        Get cached query result.

        Args:
            query: SQL query text
            params: Query parameters

        Returns:
            pd.DataFrame or None if cache miss
        """
        key = self._generate_key(query, params)

        try:
            if self.use_redis:
                # Redis cache
                data = self.redis_client.get(key)
                if data:
                    self.stats["hits"] += 1
                    logger.debug(f"Cache HIT: {key[:32]}...")
                    return pd.read_json(StringIO(data.decode("utf-8")), orient="split")
                else:
                    self.stats["misses"] += 1
                    logger.debug(f"Cache MISS: {key[:32]}...")
                    return None
            else:
                # Memory cache
                if key in self._memory_cache:
                    value, expiry = self._memory_cache[key]
                    if datetime.now() < expiry:
                        self.stats["hits"] += 1
                        logger.debug(f"Cache HIT: {key[:32]}...")
                        return value
                    else:
                        # Expired
                        del self._memory_cache[key]

                self.stats["misses"] += 1
                logger.debug(f"Cache MISS: {key[:32]}...")
                return None

        except Exception as e:
            logger.error(f"Cache get error: {e}")
            self.stats["misses"] += 1
            return None

    def set(
        self,
        query: str,
        df: pd.DataFrame,
        params: Optional[Dict] = None,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Cache query result.

        Args:
            query: SQL query text
            df: Query result DataFrame
            params: Query parameters
            ttl: TTL in seconds (None = default)

        Returns:
            bool: Success status
        """
        key = self._generate_key(query, params)
        ttl = ttl or self.default_ttl

        try:
            if self.use_redis:
                # Redis cache -- JSON serialization (safe, no arbitrary code execution)
                data = df.to_json(orient="split", date_format="iso").encode("utf-8")
                self.redis_client.setex(key, ttl, data)
                self.stats["sets"] += 1
                logger.debug(f"Cached: {key[:32]}... (TTL: {ttl}s)")
                return True
            else:
                # Memory cache
                expiry = datetime.now() + timedelta(seconds=ttl)
                self._memory_cache[key] = (df, expiry)
                self.stats["sets"] += 1
                logger.debug(f"Cached: {key[:32]}... (TTL: {ttl}s)")

                # Clean expired entries if too many
                if len(self._memory_cache) > 100:
                    self._cleanup_memory_cache()

                return True

        except Exception as e:
            logger.error(f"Cache set error: {e}")
            return False

    def delete(self, query: str, params: Optional[Dict] = None) -> bool:
        """
        Delete cached result.

        Args:
            query: SQL query text
            params: Query parameters

        Returns:
            bool: Success status
        """
        key = self._generate_key(query, params)

        try:
            if self.use_redis:
                self.redis_client.delete(key)
            else:
                if key in self._memory_cache:
                    del self._memory_cache[key]

            self.stats["deletes"] += 1
            return True

        except Exception as e:
            logger.error(f"Cache delete error: {e}")
            return False

    def clear_all(self) -> int:
        """
        Clear all cached entries.

        Returns:
            int: Number of entries cleared
        """
        try:
            if self.use_redis:
                keys = self.redis_client.keys("query_cache:*")
                if keys:
                    count = self.redis_client.delete(*keys)
                    logger.info(f"Cleared {count} Redis cache entries")
                    return count
                return 0
            else:
                count = len(self._memory_cache)
                self._memory_cache.clear()
                logger.info(f"Cleared {count} memory cache entries")
                return count

        except Exception as e:
            logger.error(f"Cache clear error: {e}")
            return 0

    def _cleanup_memory_cache(self):
        """Remove expired entries from memory cache."""
        now = datetime.now()
        expired_keys = [
            k for k, (_, expiry) in self._memory_cache.items() if now >= expiry
        ]
        for key in expired_keys:
            del self._memory_cache[key]

        if expired_keys:
            logger.debug(f"Cleaned up {len(expired_keys)} expired cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            dict: Cache performance metrics
        """
        total_requests = self.stats["hits"] + self.stats["misses"]
        hit_rate = self.stats["hits"] / total_requests if total_requests > 0 else 0

        result = {
            **self.stats,
            "total_requests": total_requests,
            "hit_rate": round(hit_rate * 100, 2),
            "backend": "redis" if self.use_redis else "memory",
        }

        if self.use_redis:
            try:
                info = self.redis_client.info("memory")
                result["memory_used_mb"] = round(
                    info.get("used_memory", 0) / (1024 * 1024), 2
                )
            except (KeyError, TypeError, ValueError) as e:
                logger.debug(f"Failed to get Redis memory stats: {e}")
                # Continue without memory stats
        else:
            result["cached_entries"] = len(self._memory_cache)

        return result


# Global cache instance
_cache_client: Optional[CacheClient] = None


def get_cache_client() -> CacheClient:
    """
    Get global cache client instance.

    Returns:
        CacheClient: Global cache instance
    """
    global _cache_client
    if _cache_client is None:
        import os

        _cache_client = CacheClient(
            redis_host=os.getenv("REDIS_HOST", "localhost"),
            redis_port=int(os.getenv("REDIS_PORT", "6379")),
            redis_db=int(os.getenv("REDIS_DB", "0")),
            default_ttl=int(os.getenv("CACHE_TTL", "3600")),
        )
    return _cache_client
