"""
Cache Router - Query result caching with Redis for performance optimization.

Provides endpoints for caching Snowflake query results, managing cache lifecycle,
and monitoring cache statistics.

Now uses UnifiedCacheClient for consistent caching across the system.
"""

import logging
import os
import time
from typing import Any, List, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

# Import unified cache client
from services.infrastructure.cache.unified_cache import get_cache_client

logger = logging.getLogger(__name__)

router = APIRouter()

# Cache configuration
CACHE_TTL = int(os.getenv("CACHE_TTL", "3600"))  # Default 1 hour


# Request/Response Models
class CacheQueryRequest(BaseModel):
    query: str = Field(..., description="SQL query to cache")
    result: Any = Field(..., description="Query result to cache")
    ttl: Optional[int] = Field(
        None, description="Time to live in seconds (default: 3600)"
    )
    tags: Optional[List[str]] = Field(
        None, description="Tags for invalidation (e.g., ['MASTER_SHOT_TABLE'])"
    )


class GetCacheRequest(BaseModel):
    query: str = Field(..., description="SQL query to lookup")


class InvalidateTagRequest(BaseModel):
    tag: str = Field(..., description="Tag to invalidate (e.g., 'MASTER_SHOT_TABLE')")


class PreWarmRequest(BaseModel):
    queries: List[str] = Field(..., description="List of queries to pre-warm")


@router.get("/", summary="Cache Service Info")
async def cache_info():
    """Get information about the cache service."""
    cache = get_cache_client()
    stats = await cache.get_stats()

    return {
        "service": "Unified Cache Service",
        "description": "Query result caching with Redis + LRU fallback",
        "redis_available": stats.get("redis_available", False),
        "backend": stats.get("backend", "unknown"),
        "default_ttl": CACHE_TTL,
        "features": {
            "auto_caching_decorator": True,
            "tag_based_invalidation": True,
            "dataframe_support": True,
            "lru_fallback": True,
            "monitoring_integration": True,
        },
    }


@router.post("/set", summary="Cache Query Result")
async def cache_query_result(request: CacheQueryRequest):
    """
    Cache a query result for performance optimization.

    Use this after executing a Snowflake query to cache the result.
    Subsequent identical queries will be served from cache instantly.
    """
    start_time = time.time()

    try:
        cache = get_cache_client()
        cache_key = cache.generate_cache_key(request.query)
        ttl = request.ttl or CACHE_TTL

        # Store in cache
        success = await cache.set(cache_key, request.result, ttl=ttl, tags=request.tags)

        if not success:
            return {
                "status": "warning",
                "message": "Cache set failed, but query result is still valid",
                "cached": False,
            }

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "message": "Query result cached successfully",
            "cache_key": cache_key[:16] + "...",  # Truncate for display
            "ttl": ttl,
            "tags": request.tags or [],
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error(f"Cache set error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "cached": False,
        }


@router.post("/get", summary="Get Cached Query Result")
async def get_cached_result(request: GetCacheRequest):
    """
    Retrieve a cached query result.

    Returns the cached result if available, otherwise returns cache_miss status.
    """
    start_time = time.time()

    try:
        cache = get_cache_client()
        cache_key = cache.generate_cache_key(request.query)

        # Get from cache
        cached_value = await cache.get(cache_key)

        if cached_value is None:
            return {
                "status": "cache_miss",
                "message": "Query result not found in cache",
                "cached": False,
            }

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "cache_hit",
            "message": "Query result retrieved from cache",
            "result": cached_value,
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error(f"Cache get error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "cached": False,
        }


@router.post("/clear", summary="Clear Entire Cache")
async def clear_cache():
    """
    Clear all cached query results.

    **Warning**: This clears ALL cached data. Use with caution.
    """
    start_time = time.time()

    try:
        cache = get_cache_client()
        keys_deleted = await cache.clear_all()

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "message": f"Cache cleared: {keys_deleted} keys deleted",
            "keys_deleted": keys_deleted,
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error(f"Cache clear error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


@router.post("/invalidate", summary="Invalidate Cache by Tag")
async def invalidate_by_tag(request: InvalidateTagRequest):
    """
    Invalidate all cached queries with a specific tag.

    Example: After refreshing MASTER_SHOT_TABLE, invalidate all queries tagged with 'MASTER_SHOT_TABLE'.
    """
    start_time = time.time()

    try:
        cache = get_cache_client()
        keys_invalidated = await cache.invalidate_by_tag(request.tag)

        execution_time_ms = (time.time() - start_time) * 1000

        return {
            "status": "success",
            "message": f"Invalidated {keys_invalidated} cached queries with tag '{request.tag}'",
            "tag": request.tag,
            "keys_invalidated": keys_invalidated,
            "metadata": {
                "execution_time_ms": execution_time_ms,
            },
        }

    except Exception as e:
        logger.error(f"Cache invalidate error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


@router.get("/stats", summary="Get Cache Statistics")
async def get_cache_stats():
    """
    Get cache statistics and performance metrics.

    Returns information about cache size, memory usage, hit rates, and backend type.
    """
    start_time = time.time()

    try:
        cache = get_cache_client()
        stats = await cache.get_stats()

        execution_time_ms = (time.time() - start_time) * 1000
        stats["metadata"] = {"execution_time_ms": execution_time_ms}
        stats["status"] = "success"

        return stats

    except Exception as e:
        logger.error(f"Cache stats error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
        }


@router.post("/prewarm", summary="Pre-warm Cache")
async def prewarm_cache(request: PreWarmRequest):
    """
    Pre-warm cache with common queries.

    **Note**: This endpoint only marks queries for pre-warming.
    Actual query execution should be done separately.
    """
    return {
        "status": "info",
        "message": "Pre-warming requires query execution. Use this as a reminder to run common queries.",
        "queries_to_execute": request.queries,
        "suggestion": "Execute these queries via /database/query endpoint to populate cache",
        "tip": "Or use the @cached() decorator in your analytics functions for automatic caching",
    }
