"""
Rate Limiting Middleware

Provides request rate limiting to prevent abuse and ensure fair resource usage.
"""

import logging
import os
import time
from collections import defaultdict
from typing import Callable, Dict, Tuple

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

logger = logging.getLogger(__name__)

# Read-only, idempotent methods are not rate limited: throttling exists to
# protect against abusive writes, and exempting reads keeps dashboards that
# fan out many GETs from tripping the shared per-client limit.
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})


class RateLimitMiddleware(BaseHTTPMiddleware):
    """
    Simple in-memory rate limiter using sliding window algorithm.

    For production with multiple workers, consider using Redis-based rate limiting.
    """

    def __init__(self, app, default_limit: str = "100/minute"):
        """
        Initialize rate limiter.

        Args:
            app: FastAPI application
            default_limit: Default rate limit in format "count/period"
                          (e.g., "100/minute", "1000/hour")
        """
        super().__init__(app)
        self.default_limit = default_limit
        self.enabled = os.getenv("RATE_LIMIT_ENABLED", "True").lower() == "true"

        # Parse default limit
        self.limit_count, self.limit_period = self._parse_limit(default_limit)

        # Storage: client_ip -> list of request timestamps
        self.request_history: Dict[str, list] = defaultdict(list)

        # Cleanup old entries every 5 minutes
        self.last_cleanup = time.time()
        self.cleanup_interval = 300  # 5 minutes

        logger.info(
            f"Rate limiting {'enabled' if self.enabled else 'disabled'}: "
            f"{self.limit_count} requests per {self.limit_period} seconds"
        )

    def _parse_limit(self, limit_str: str) -> Tuple[int, int]:
        """
        Parse limit string into count and period in seconds.

        Args:
            limit_str: Limit string (e.g., "100/minute")

        Returns:
            Tuple of (count, period_in_seconds)
        """
        try:
            count, period = limit_str.split("/")
            count = int(count)

            period_map = {
                "second": 1,
                "minute": 60,
                "hour": 3600,
                "day": 86400,
            }

            period_seconds = period_map.get(period.lower(), 60)
            return count, period_seconds
        except Exception as e:
            logger.error(f"Failed to parse rate limit '{limit_str}': {e}")
            return 100, 60  # Default fallback

    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier from request.

        Uses X-Forwarded-For header if behind proxy, otherwise uses client IP.

        Args:
            request: FastAPI request

        Returns:
            Client identifier string
        """
        # Check for forwarded header (if behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()

        # Fall back to client IP
        return request.client.host if request.client else "unknown"

    def _cleanup_old_entries(self):
        """Remove old request history entries to prevent memory bloat."""
        current_time = time.time()

        # Only cleanup every 5 minutes
        if current_time - self.last_cleanup < self.cleanup_interval:
            return

        cutoff_time = current_time - (self.limit_period * 2)  # Keep 2x window

        for client_id in list(self.request_history.keys()):
            # Remove timestamps older than cutoff
            self.request_history[client_id] = [
                ts for ts in self.request_history[client_id] if ts > cutoff_time
            ]

            # Remove client entirely if no recent requests
            if not self.request_history[client_id]:
                del self.request_history[client_id]

        self.last_cleanup = current_time
        logger.debug(f"Rate limit cleanup: {len(self.request_history)} active clients")

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process request with rate limiting.

        Args:
            request: Incoming request
            call_next: Next middleware/handler

        Returns:
            Response. A 429 JSONResponse is returned directly (not raised) when
            the limit is exceeded, because exceptions raised inside a
            BaseHTTPMiddleware.dispatch are not routed through the app's
            exception handlers and would surface to the client as a 500.
        """
        # Skip if disabled
        if not self.enabled:
            return await call_next(request)

        # Skip read-only requests: only state-changing verbs are throttled.
        if request.method in SAFE_METHODS:
            return await call_next(request)

        # Skip rate limiting for health check
        if request.url.path in ["/", "/health", "/docs", "/openapi.json", "/redoc"]:
            return await call_next(request)

        # Get client ID
        client_id = self._get_client_id(request)
        current_time = time.time()

        # Get request history for this client
        history = self.request_history[client_id]

        # Remove timestamps outside the sliding window
        cutoff_time = current_time - self.limit_period
        history[:] = [ts for ts in history if ts > cutoff_time]

        # Check if limit exceeded
        if len(history) >= self.limit_count:
            # Calculate retry-after time
            oldest_request = history[0]
            retry_after = int(oldest_request + self.limit_period - current_time) + 1

            logger.warning(
                f"Rate limit exceeded for {client_id}: "
                f"{len(history)} requests in {self.limit_period}s window"
            )

            return JSONResponse(
                status_code=HTTP_429_TOO_MANY_REQUESTS,
                content={
                    "error": "Rate limit exceeded",
                    "limit": f"{self.limit_count} requests per {self.limit_period} seconds",
                    "retry_after": retry_after,
                },
                headers={"Retry-After": str(retry_after)},
            )

        # Add current request timestamp
        history.append(current_time)

        # Periodic cleanup
        self._cleanup_old_entries()

        # Add rate limit headers to response
        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit_count)
        response.headers["X-RateLimit-Remaining"] = str(
            max(0, self.limit_count - len(history))
        )
        response.headers["X-RateLimit-Reset"] = str(
            int(history[0] + self.limit_period) if history else int(current_time)
        )

        return response
