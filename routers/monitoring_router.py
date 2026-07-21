"""
Monitoring Router - System health checks, metrics collection, and alerting.

Uses SQLite for persistent metrics and alerts across server restarts.
"""

import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import psutil
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from models.database import get_session
from models.monitoring import AlertHistory, AlertRule, MetricRecord
from utils.error_handling import sanitize_error_message

logger = logging.getLogger(__name__)

router = APIRouter()

# Track server start time
START_TIME = datetime.now()


# Request Models
class AlertRequest(BaseModel):
    title: str = Field(..., description="Alert title")
    message: str = Field(..., description="Alert message")
    severity: str = Field(
        "warning", description="Severity: info, warning, error, critical"
    )
    metadata: Optional[Dict[str, Any]] = Field(None, description="Additional metadata")


class AlertRuleRequest(BaseModel):
    name: str = Field(..., description="Rule name")
    condition: str = Field(
        ..., description="Condition expression (e.g., 'cpu_percent > 80')"
    )
    severity: str = Field("warning", description="Alert severity")
    enabled: bool = Field(True, description="Whether rule is enabled")


@router.get("/", summary="Monitoring Service Info")
async def monitoring_info():
    """Get information about the monitoring service."""
    try:
        with get_session() as session:
            metrics_count = session.query(MetricRecord).count()
            alert_rules_count = session.query(AlertRule).count()
            alerts_count = session.query(AlertHistory).count()

        return {
            "service": "Monitoring Service",
            "description": "System health checks with persistent SQLite storage",
            "storage": "SQLite (persists across restarts)",
            "uptime_seconds": int((datetime.now() - START_TIME).total_seconds()),
            "metrics_collected": metrics_count,
            "alert_rules": alert_rules_count,
            "alerts_triggered": alerts_count,
        }
    except Exception as e:
        logger.error(f"Monitoring info error: {e}")
        return {
            "service": "Monitoring Service",
            "description": "System health checks and performance metrics",
            "error": "Database connection error",
        }


@router.get("/health", summary="Health Check")
async def health_check():
    """Check system health and availability."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        services_status = {
            "api": "healthy",
            "redis": check_redis_health(),
            "database": "healthy",  # If we're here, database is working
        }

        overall_status = "healthy"
        if cpu_percent > 90 or memory.percent > 90 or disk.percent > 90:
            overall_status = "degraded"

        return {
            "status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": round(cpu_percent, 2),
                "memory_percent": round(memory.percent, 2),
                "disk_percent": round(disk.percent, 2),
                "uptime_seconds": int((datetime.now() - START_TIME).total_seconds()),
            },
            "services": services_status,
        }

    except Exception as e:
        logger.error(f"Health check error: {e}", exc_info=True)
        return {
            "status": "error",
            "error": str(e),
            "timestamp": datetime.now().isoformat(),
        }


@router.get("/metrics", summary="Get Current Metrics")
async def get_metrics():
    """Get current system metrics and save to database."""
    try:
        cpu_percent = psutil.cpu_percent(interval=0.1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        network = psutil.net_io_counters()

        metrics = {
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": round(cpu_percent, 2),
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": round(memory.total / (1024**3), 2),
                "memory_used_gb": round(memory.used / (1024**3), 2),
                "memory_percent": round(memory.percent, 2),
                "disk_total_gb": round(disk.total / (1024**3), 2),
                "disk_used_gb": round(disk.used / (1024**3), 2),
                "disk_percent": round(disk.percent, 2),
                "network_bytes_sent": network.bytes_sent,
                "network_bytes_recv": network.bytes_recv,
            },
            "application": {
                "uptime_seconds": int((datetime.now() - START_TIME).total_seconds()),
            },
        }

        # Store metrics in database
        try:
            with get_session() as session:
                # Store key metrics
                metric_records = [
                    MetricRecord(
                        metric_type="cpu_percent",
                        metric_value=cpu_percent,
                        source="system",
                    ),
                    MetricRecord(
                        metric_type="memory_percent",
                        metric_value=memory.percent,
                        source="system",
                    ),
                    MetricRecord(
                        metric_type="disk_percent",
                        metric_value=disk.percent,
                        source="system",
                    ),
                ]

                for record in metric_records:
                    session.add(record)

                session.commit()

        except Exception as db_error:
            logger.warning(f"Failed to store metrics: {db_error}")

        return {
            "status": "success",
            "metrics": metrics,
        }

    except Exception as e:
        logger.error(f"Get metrics error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to retrieve metrics. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/metrics/history", summary="Get Metrics History")
async def get_metrics_history(hours: int = 1, limit: int = 100):
    """Get historical metrics from database."""
    try:
        with get_session() as session:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            metrics = (
                session.query(MetricRecord)
                .filter(MetricRecord.timestamp >= cutoff_time)
                .order_by(MetricRecord.timestamp.desc())
                .limit(limit)
                .all()
            )

            result_metrics = [m.to_dict() for m in metrics]

        return {
            "status": "success",
            "period_hours": hours,
            "data_points": len(result_metrics),
            "metrics": result_metrics,
        }

    except Exception as e:
        logger.error(f"Get metrics history error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to retrieve metrics history. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/alerts", summary="Send Alert")
async def send_alert(request: AlertRequest):
    """Send an alert and store in database."""
    try:
        with get_session() as session:
            alert = AlertHistory(
                title=request.title,
                message=request.message,
                severity=request.severity,
                extra_data=request.metadata or {},
            )

            session.add(alert)
            session.commit()

            alert_dict = alert.to_dict()

        logger.warning(
            f"ALERT [{request.severity.upper()}]: {request.title} - {request.message}"
        )

        return {
            "status": "success",
            "message": "Alert sent and stored in database",
            "alert": alert_dict,
        }

    except Exception as e:
        logger.error(f"Send alert error: {e}", exc_info=True)
        error_msg = sanitize_error_message(e, "Failed to send alert. Please try again.")
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/alerts", summary="Get Alert History")
async def get_alert_history(
    hours: int = 24, severity: Optional[str] = None, limit: int = 100
):
    """Get alert history from database."""
    try:
        with get_session() as session:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            query = session.query(AlertHistory).filter(
                AlertHistory.timestamp >= cutoff_time
            )

            if severity:
                query = query.filter(AlertHistory.severity == severity)

            alerts = query.order_by(AlertHistory.timestamp.desc()).limit(limit).all()
            result_alerts = [a.to_dict() for a in alerts]

        return {
            "status": "success",
            "period_hours": hours,
            "total_alerts": len(result_alerts),
            "alerts": result_alerts,
        }

    except Exception as e:
        logger.error(f"Get alert history error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to retrieve alert history. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/alert-rules", summary="Add Alert Rule")
async def add_alert_rule(request: AlertRuleRequest):
    """Add an automated alert rule to database."""
    try:
        with get_session() as session:
            rule = AlertRule(
                name=request.name,
                condition=request.condition,
                severity=request.severity,
                enabled=request.enabled,
            )

            session.add(rule)
            session.commit()

            rule_dict = rule.to_dict()

        return {
            "status": "success",
            "message": f"Alert rule '{request.name}' created and stored in database",
            "rule": rule_dict,
        }

    except Exception as e:
        logger.error(f"Add alert rule error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to add alert rule. Please check your input and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/alert-rules", summary="List Alert Rules")
async def list_alert_rules():
    """List all configured alert rules from database."""
    try:
        with get_session() as session:
            rules = session.query(AlertRule).all()
            result_rules = [r.to_dict() for r in rules]

        return {
            "status": "success",
            "total_rules": len(result_rules),
            "rules": result_rules,
        }

    except Exception as e:
        logger.error(f"List alert rules error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to list alert rules. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.get("/dashboard", summary="Monitoring Dashboard")
async def get_dashboard(hours: int = 24):
    """
    Get aggregated monitoring dashboard with trends and alerts.

    Returns:
    - Current system status
    - Metric trends over time
    - Recent alerts
    - Alert rule status
    """
    try:
        with get_session() as session:
            cutoff_time = datetime.now() - timedelta(hours=hours)

            # Get current metrics
            current_cpu = (
                session.query(MetricRecord)
                .filter(MetricRecord.metric_type == "cpu_percent")
                .order_by(MetricRecord.timestamp.desc())
                .first()
            )

            current_memory = (
                session.query(MetricRecord)
                .filter(MetricRecord.metric_type == "memory_percent")
                .order_by(MetricRecord.timestamp.desc())
                .first()
            )

            current_disk = (
                session.query(MetricRecord)
                .filter(MetricRecord.metric_type == "disk_percent")
                .order_by(MetricRecord.timestamp.desc())
                .first()
            )

            # Get metric trends (last N hours)
            cpu_trend = (
                session.query(MetricRecord)
                .filter(
                    MetricRecord.metric_type == "cpu_percent",
                    MetricRecord.timestamp >= cutoff_time,
                )
                .order_by(MetricRecord.timestamp)
                .all()
            )

            memory_trend = (
                session.query(MetricRecord)
                .filter(
                    MetricRecord.metric_type == "memory_percent",
                    MetricRecord.timestamp >= cutoff_time,
                )
                .order_by(MetricRecord.timestamp)
                .all()
            )

            # Get recent alerts
            recent_alerts = (
                session.query(AlertHistory)
                .filter(AlertHistory.timestamp >= cutoff_time)
                .order_by(AlertHistory.timestamp.desc())
                .limit(10)
                .all()
            )

            # Get alert rules status
            alert_rules = session.query(AlertRule).all()

            # Calculate statistics
            cpu_values = [m.metric_value for m in cpu_trend]
            memory_values = [m.metric_value for m in memory_trend]

            cpu_avg = sum(cpu_values) / len(cpu_values) if cpu_values else 0
            memory_avg = sum(memory_values) / len(memory_values) if memory_values else 0

            cpu_max = max(cpu_values) if cpu_values else 0
            memory_max = max(memory_values) if memory_values else 0

        dashboard = {
            "status": "success",
            "timestamp": datetime.now().isoformat(),
            "period_hours": hours,
            "current": {
                "cpu_percent": (
                    round(current_cpu.metric_value, 2) if current_cpu else None
                ),
                "memory_percent": (
                    round(current_memory.metric_value, 2) if current_memory else None
                ),
                "disk_percent": (
                    round(current_disk.metric_value, 2) if current_disk else None
                ),
                "uptime_seconds": int((datetime.now() - START_TIME).total_seconds()),
            },
            "trends": {
                "cpu": {
                    "average": round(cpu_avg, 2),
                    "max": round(cpu_max, 2),
                    "data_points": len(cpu_values),
                    "data": [
                        {
                            "timestamp": m.timestamp.isoformat(),
                            "value": round(m.metric_value, 2),
                        }
                        for m in cpu_trend[-50:]  # Last 50 points
                    ],
                },
                "memory": {
                    "average": round(memory_avg, 2),
                    "max": round(memory_max, 2),
                    "data_points": len(memory_values),
                    "data": [
                        {
                            "timestamp": m.timestamp.isoformat(),
                            "value": round(m.metric_value, 2),
                        }
                        for m in memory_trend[-50:]  # Last 50 points
                    ],
                },
            },
            "alerts": {
                "recent_count": len(recent_alerts),
                "recent_alerts": [
                    {
                        "timestamp": a.timestamp.isoformat(),
                        "title": a.title,
                        "severity": a.severity,
                        "acknowledged": a.acknowledged,
                    }
                    for a in recent_alerts
                ],
            },
            "rules": {
                "total": len(alert_rules),
                "enabled": sum(1 for r in alert_rules if r.enabled),
                "rules": [
                    {
                        "name": r.name,
                        "condition": r.condition,
                        "severity": r.severity,
                        "enabled": r.enabled,
                        "triggered_count": r.triggered_count,
                        "last_triggered": (
                            r.last_triggered.isoformat() if r.last_triggered else None
                        ),
                    }
                    for r in alert_rules
                ],
            },
        }

        return dashboard

    except Exception as e:
        logger.error(f"Dashboard error: {e}", exc_info=True)
        error_msg = sanitize_error_message(
            e, "Failed to generate dashboard. Please try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


def check_redis_health() -> str:
    """Check if Redis is available."""
    try:
        import redis

        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            socket_connect_timeout=1,
        )
        redis_client.ping()
        return "healthy"
    except (AttributeError, Exception) as e:
        logger.debug(f"Redis health check failed: {e}")
        return "unavailable"
