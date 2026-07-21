"""
Health Monitor for MCP Server Ecosystem.

Features:
- Health checks for all MCP servers
- Service availability monitoring
- Dependency checks (Redis, Snowflake)
- Performance metrics collection
- Real-time status tracking

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
import os
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class HealthStatus:
    """Health status for a service."""

    service: str
    status: str  # "healthy", "degraded", "unhealthy"
    response_time_ms: Optional[float] = None
    last_check: Optional[str] = None
    error_message: Optional[str] = None
    details: Optional[Dict] = None


class HealthMonitor:
    """
    Health Monitor for MCP Server Ecosystem.

    Monitors health of all MCP servers and their dependencies.
    """

    def __init__(self):
        """Initialize Health Monitor."""
        self.last_check_time = None
        self.health_history: List[Dict] = []
        self.max_history = 100
        logger.info("✅ Health Monitor initialized")

    async def check_all_services(self) -> Dict[str, Any]:
        """
        Check health of all services.

        Returns:
            dict: Overall health status with individual service details
        """
        self.last_check_time = datetime.now()

        checks = {
            "redis": await self._check_redis(),
            "snowflake": await self._check_snowflake(),
            "auth_mcp": await self._check_auth_mcp(),
            "audit_mcp": await self._check_audit_mcp(),
            "analytics_mcp": await self._check_analytics_mcp(),
            "cache": await self._check_cache(),
        }

        # Calculate overall status
        statuses = [check.status for check in checks.values()]
        if all(s == "healthy" for s in statuses):
            overall_status = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            overall_status = "unhealthy"
        else:
            overall_status = "degraded"

        result = {
            "overall_status": overall_status,
            "timestamp": self.last_check_time.isoformat(),
            "services": {name: asdict(status) for name, status in checks.items()},
        }

        # Store in history
        self._add_to_history(result)

        return result

    async def _check_redis(self) -> HealthStatus:
        """Check Redis health."""
        start_time = time.time()

        try:
            from services.infrastructure.cache.redis_client import get_cache_client

            cache = get_cache_client()
            if cache.use_redis:
                # Test connection
                cache.redis_client.ping()
                response_time = (time.time() - start_time) * 1000

                # Get Redis info
                info = cache.redis_client.info("memory")
                memory_used_mb = round(info.get("used_memory", 0) / (1024 * 1024), 2)

                return HealthStatus(
                    service="redis",
                    status="healthy",
                    response_time_ms=response_time,
                    last_check=datetime.now().isoformat(),
                    details={
                        "backend": "redis",
                        "memory_used_mb": memory_used_mb,
                    },
                )
            else:
                return HealthStatus(
                    service="redis",
                    status="degraded",
                    last_check=datetime.now().isoformat(),
                    error_message="Redis not available, using in-memory fallback",
                    details={"backend": "memory"},
                )

        except Exception as e:
            return HealthStatus(
                service="redis",
                status="unhealthy",
                last_check=datetime.now().isoformat(),
                error_message=str(e),
            )

    async def _check_snowflake(self) -> HealthStatus:
        """Check Snowflake health."""
        start_time = time.time()

        try:
            from services.infrastructure.snowflake.session_pool import get_session_pool

            pool = get_session_pool()

            # Test query
            pool.execute_query("SELECT CURRENT_TIMESTAMP()")
            response_time = (time.time() - start_time) * 1000

            return HealthStatus(
                service="snowflake",
                status="healthy",
                response_time_ms=response_time,
                last_check=datetime.now().isoformat(),
                details={
                    "database": pool.main_database,
                    "warehouse": os.getenv("SNOWFLAKE_WAREHOUSE", "unknown"),
                },
            )

        except Exception as e:
            return HealthStatus(
                service="snowflake",
                status="unhealthy",
                last_check=datetime.now().isoformat(),
                error_message=str(e),
            )

    async def _check_auth_mcp(self) -> HealthStatus:
        """Check Auth MCP Server health.

        NOTE: MCP servers have been removed in favor of unified API.
        This check is disabled but kept for backward compatibility.
        """
        return HealthStatus(
            service="auth_mcp",
            status="degraded",
            last_check=datetime.now().isoformat(),
            error_message="MCP server architecture deprecated - using unified API",
            details={"note": "Auth functionality available via /auth endpoints"},
        )

    async def _check_audit_mcp(self) -> HealthStatus:
        """Check Audit MCP Server health.

        NOTE: MCP servers have been removed in favor of unified API.
        This check is disabled but kept for backward compatibility.
        """
        return HealthStatus(
            service="audit_mcp",
            status="degraded",
            last_check=datetime.now().isoformat(),
            error_message="MCP server architecture deprecated - using unified API",
            details={"note": "Audit functionality available via /audit endpoints"},
        )

    async def _check_analytics_mcp(self) -> HealthStatus:
        """Check Analytics MCP Server health.

        NOTE: MCP servers have been removed in favor of unified API.
        This check is disabled but kept for backward compatibility.
        """
        return HealthStatus(
            service="analytics_mcp",
            status="degraded",
            last_check=datetime.now().isoformat(),
            error_message="MCP server architecture deprecated - using unified API",
            details={
                "note": "Analytics functionality available via /analytics endpoints"
            },
        )

    async def _check_cache(self) -> HealthStatus:
        """Check cache performance."""
        start_time = time.time()

        try:
            from services.infrastructure.cache.redis_client import get_cache_client

            cache = get_cache_client()
            stats = cache.get_stats()
            response_time = (time.time() - start_time) * 1000

            # Determine health based on hit rate
            hit_rate = stats.get("hit_rate", 0)
            if hit_rate >= 70:
                status = "healthy"
            elif hit_rate >= 40:
                status = "degraded"
            else:
                status = "healthy"  # Still healthy, just low hit rate

            return HealthStatus(
                service="cache",
                status=status,
                response_time_ms=response_time,
                last_check=datetime.now().isoformat(),
                details=stats,
            )

        except Exception as e:
            return HealthStatus(
                service="cache",
                status="unhealthy",
                last_check=datetime.now().isoformat(),
                error_message=str(e),
            )

    def _add_to_history(self, result: Dict):
        """Add health check result to history."""
        self.health_history.append(result)

        # Keep only last N checks
        if len(self.health_history) > self.max_history:
            self.health_history = self.health_history[-self.max_history :]

    def get_history(self, limit: int = 10) -> List[Dict]:
        """Get recent health check history."""
        return self.health_history[-limit:]

    def get_metrics_summary(self) -> Dict[str, Any]:
        """
        Get aggregated metrics from recent health checks.

        Returns:
            dict: Metrics summary
        """
        if not self.health_history:
            return {"status": "no_data", "message": "No health check history available"}

        # Calculate uptime percentage per service
        service_stats = {}

        for check in self.health_history:
            for service_name, service_data in check["services"].items():
                if service_name not in service_stats:
                    service_stats[service_name] = {
                        "total_checks": 0,
                        "healthy_checks": 0,
                        "avg_response_time_ms": [],
                    }

                service_stats[service_name]["total_checks"] += 1
                if service_data["status"] == "healthy":
                    service_stats[service_name]["healthy_checks"] += 1

                if service_data.get("response_time_ms"):
                    service_stats[service_name]["avg_response_time_ms"].append(
                        service_data["response_time_ms"]
                    )

        # Calculate percentages and averages
        summary = {}
        for service, stats in service_stats.items():
            uptime_pct = (
                (stats["healthy_checks"] / stats["total_checks"] * 100)
                if stats["total_checks"] > 0
                else 0
            )

            avg_response = 0
            if stats["avg_response_time_ms"]:
                avg_response = sum(stats["avg_response_time_ms"]) / len(
                    stats["avg_response_time_ms"]
                )

            summary[service] = {
                "uptime_percentage": round(uptime_pct, 2),
                "total_checks": stats["total_checks"],
                "healthy_checks": stats["healthy_checks"],
                "avg_response_time_ms": round(avg_response, 2),
            }

        return {
            "status": "success",
            "period_checks": len(self.health_history),
            "services": summary,
        }


# Global health monitor instance
_health_monitor: Optional[HealthMonitor] = None


def get_health_monitor() -> HealthMonitor:
    """
    Get global health monitor instance.

    Returns:
        HealthMonitor: Global health monitor instance
    """
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = HealthMonitor()
    return _health_monitor
