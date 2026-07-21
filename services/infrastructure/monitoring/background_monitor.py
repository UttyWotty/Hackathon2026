"""
Background Monitoring - Collects metrics and evaluates alert rules.

This module runs continuously in the background:
- Collects system metrics every 60 seconds
- Stores metrics in SQLite
- Evaluates alert rules
- Triggers alerts when conditions met
- Cleans up old metrics

Architecture:
- Runs as asyncio background task
- Polls system metrics using psutil
- Checks Snowflake/Redis health
- Evaluates alert rules from database
- Sends real alerts via email
- Cleans metrics older than 30 days

Author: Utku Gulbardak
Date: 2025-11-24
"""

import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Any, Dict

import psutil

logger = logging.getLogger(__name__)

# Global monitoring state
_monitor_running = False


async def start_monitor():
    """
    Start the background monitoring loop.

    This runs continuously, collecting metrics and evaluating rules.
    """
    global _monitor_running
    _monitor_running = True

    logger.info("📊 Background monitoring loop starting...")

    # Initialize default rules
    await _initialize_default_rules()

    collect_interval = 60  # Collect metrics every 60 seconds
    cleanup_interval = 3600  # Cleanup every hour

    last_cleanup = datetime.now()

    while _monitor_running:
        try:
            # Collect metrics and evaluate rules
            await _collect_and_evaluate()

            # Cleanup old metrics (every hour)
            if (datetime.now() - last_cleanup).total_seconds() >= cleanup_interval:
                await _cleanup_old_metrics()
                last_cleanup = datetime.now()

            await asyncio.sleep(collect_interval)

        except asyncio.CancelledError:
            logger.info("📊 Monitoring loop cancelled")
            break
        except Exception as e:
            logger.error(f"❌ Monitoring loop error: {e}", exc_info=True)
            await asyncio.sleep(collect_interval)  # Continue despite errors


def stop_monitor():
    """Stop the monitoring loop."""
    global _monitor_running
    _monitor_running = False
    logger.info("📊 Monitoring stop requested")


async def _collect_and_evaluate():
    """
    Collect current metrics and evaluate alert rules.

    This is the main monitoring logic:
    1. Collect system metrics (CPU, memory, disk)
    2. Check service health (Redis, Snowflake)
    3. Store metrics in database
    4. Evaluate all enabled alert rules
    5. Trigger alerts if conditions met
    """
    try:
        from models.database import get_session
        from models.monitoring import AlertRule, MetricRecord

        # Collect system metrics
        cpu_percent = psutil.cpu_percent(
            interval=1.0
        )  # 1 second interval for more stable measurement
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage("/")

        # Check service health
        redis_healthy = _check_redis_health()
        snowflake_healthy = _check_snowflake_health()

        # Store metrics in database
        with get_session() as session:
            metrics_data = [
                {"type": "cpu_percent", "value": cpu_percent, "source": "system"},
                {"type": "memory_percent", "value": memory.percent, "source": "system"},
                {
                    "type": "memory_available_gb",
                    "value": memory.available / (1024**3),
                    "source": "system",
                },
                {"type": "disk_percent", "value": disk.percent, "source": "system"},
                {
                    "type": "disk_free_gb",
                    "value": disk.free / (1024**3),
                    "source": "system",
                },
                {
                    "type": "redis_healthy",
                    "value": 1.0 if redis_healthy else 0.0,
                    "source": "service",
                },
                {
                    "type": "snowflake_healthy",
                    "value": 1.0 if snowflake_healthy else 0.0,
                    "source": "service",
                },
            ]

            # Create metric records
            for metric_data in metrics_data:
                record = MetricRecord(
                    metric_type=metric_data["type"],
                    metric_value=metric_data["value"],
                    source=metric_data["source"],
                )
                session.add(record)

            session.commit()

            # Create metrics dict for rule evaluation
            current_metrics = {m["type"]: m["value"] for m in metrics_data}

            # Get all enabled alert rules
            rules = session.query(AlertRule).filter(AlertRule.enabled).all()

            # Evaluate each rule
            for rule in rules:
                try:
                    if _evaluate_rule(rule, current_metrics):
                        # Check if alert should be throttled (only alert once per hour)
                        should_alert = _should_trigger_alert(rule)

                        if should_alert:
                            # Rule triggered - send alert
                            await _trigger_alert(rule, current_metrics)

                            # Update rule tracking
                            rule.triggered_count = (rule.triggered_count or 0) + 1
                            rule.last_triggered = datetime.now()
                            session.commit()
                        else:
                            # Alert throttled - still log but don't spam
                            logger.debug(
                                f"Alert '{rule.name}' triggered but throttled "
                                f"(last triggered: {rule.last_triggered})"
                            )

                except Exception as rule_error:
                    logger.error(f"Error evaluating rule '{rule.name}': {rule_error}")

    except Exception as e:
        logger.error(f"❌ Error collecting metrics: {e}", exc_info=True)


def _evaluate_rule(rule: Any, metrics: Dict[str, float]) -> bool:
    """
    Evaluate an alert rule against current metrics.

    Supports conditions like:
    - cpu_percent > 90
    - memory_percent > 85
    - disk_percent > 95
    - snowflake_healthy == 0

    Args:
        rule: AlertRule from database
        metrics: Current metric values

    Returns:
        True if rule condition met, False otherwise
    """
    try:
        condition = rule.condition.strip()

        # Parse condition: "metric_name operator value"
        # Support operators: >, <, >=, <=, ==, !=
        operators = [">=", "<=", "==", "!=", ">", "<"]

        metric_name = None
        operator = None
        threshold = None

        for op in operators:
            if op in condition:
                parts = condition.split(op)
                if len(parts) == 2:
                    metric_name = parts[0].strip()
                    operator = op
                    threshold = float(parts[1].strip())
                    break

        if not metric_name or operator is None or threshold is None:
            logger.warning(f"Invalid rule condition: {condition}")
            return False

        # Get current metric value
        current_value = metrics.get(metric_name)

        if current_value is None:
            logger.warning(f"Metric '{metric_name}' not found in current metrics")
            return False

        # Evaluate condition
        if operator == ">":
            return current_value > threshold
        elif operator == "<":
            return current_value < threshold
        elif operator == ">=":
            return current_value >= threshold
        elif operator == "<=":
            return current_value <= threshold
        elif operator == "==":
            return current_value == threshold
        elif operator == "!=":
            return current_value != threshold

        return False

    except Exception as e:
        logger.error(f"Error evaluating rule: {e}")
        return False


def _should_trigger_alert(rule: Any) -> bool:
    """
    Check if alert should be triggered based on throttling rules.

    Prevents alert spam by only allowing alerts once per hour per rule.

    Args:
        rule: AlertRule from database

    Returns:
        True if alert should be triggered, False if throttled
    """
    if not rule.last_triggered:
        # Never triggered before - allow alert
        return True

    # Check if last alert was more than 1 hour ago
    time_since_last = datetime.now() - rule.last_triggered
    return time_since_last >= timedelta(hours=1)


async def _trigger_alert(rule: Any, metrics: Dict[str, float]):
    """
    Trigger an alert by sending email and storing in history.

    Args:
        rule: AlertRule that triggered
        metrics: Current metric values
    """
    try:

        from models.database import get_session
        from models.monitoring import AlertHistory

        # Create alert message
        title = f"🚨 Alert: {rule.name}"
        message = f"Alert rule '{rule.name}' triggered.\n\nCondition: {rule.condition}\n\nCurrent metrics:\n"

        for metric_name, value in metrics.items():
            message += f"  • {metric_name}: {value:.2f}\n"

        # Store in alert history
        with get_session() as session:
            alert = AlertHistory(
                title=title,
                message=message,
                severity=rule.severity,
                rule_id=rule.id,
                extra_data=metrics,
            )

            session.add(alert)
            session.commit()

        logger.warning(
            f"ALERT [{rule.severity.upper()}]: {rule.name} - {rule.condition}"
        )

        # Send email if configured
        await _send_alert_email(title, message, rule.severity)

        # Send Google Chat alert if configured
        from services.infrastructure.google_chat.alert_sender import (
            send_alert as send_chat_alert,
        )

        send_chat_alert(
            title=title,
            message=message,
            severity=rule.severity,
            source="monitoring",
            alert_key=f"monitor:{rule.name}",
            extra_fields={k: f"{v:.2f}" for k, v in metrics.items()},
        )

    except Exception as e:
        logger.error(f"Error triggering alert: {e}", exc_info=True)


async def _send_alert_email(title: str, message: str, severity: str):
    """
    Send alert via email system.

    Args:
        title: Alert title
        message: Alert message
        severity: Alert severity
    """
    try:
        import requests

        # Get alert email from environment
        alert_email = os.getenv("ALERT_EMAIL")
        if not alert_email:
            logger.debug("No ALERT_EMAIL configured, skipping email")
            return

        # Call email API (async, don't wait)
        email_data = {
            "recipient_email": alert_email,
            "subject": title,
            "template_name": "alert",
            "template_data": {
                "title": title,
                "message": message,
                "severity": severity,
                "timestamp": datetime.now().isoformat(),
            },
        }

        try:
            from utils.error_handling import get_api_base_url

            api_url = get_api_base_url()
            requests.post(f"{api_url}/email/send-template", json=email_data, timeout=5)
            logger.info(f"Alert email sent to {alert_email}")
        except (requests.RequestException, ConnectionError, TimeoutError) as e:
            logger.warning(f"Failed to send alert email: {e}")
            # Don't fail if email fails - monitoring should continue

    except Exception as e:
        logger.debug(f"Email send error: {e}")


async def _cleanup_old_metrics():
    """
    Clean up metrics older than 30 days.

    Keeps database size manageable while retaining recent data for trends.
    """
    try:
        from models.database import get_session
        from models.monitoring import MetricRecord

        with get_session() as session:
            # Delete metrics older than 30 days
            cutoff_date = datetime.now() - timedelta(days=30)

            deleted_count = (
                session.query(MetricRecord)
                .filter(MetricRecord.timestamp < cutoff_date)
                .delete()
            )

            session.commit()

        if deleted_count > 0:
            logger.info(f"🧹 Cleaned up {deleted_count} old metrics (>30 days)")

    except Exception as e:
        logger.error(f"Error cleaning up metrics: {e}", exc_info=True)


async def _initialize_default_rules():
    """
    Initialize default alert rules if none exist.

    Creates manufacturing-specific alert rules:
    - High CPU usage
    - High memory usage
    - Low disk space
    - Service down (Redis, Snowflake)
    """
    try:
        from models.database import get_session
        from models.monitoring import AlertRule

        with get_session() as session:
            # Check if rules already exist
            existing_count = session.query(AlertRule).count()

            if existing_count > 0:
                logger.info(f"📋 {existing_count} alert rule(s) already configured")
                return

            # Create default rules
            default_rules = [
                {
                    "name": "High CPU Usage",
                    "condition": "cpu_percent > 90",
                    "severity": "warning",
                    "enabled": True,
                    "extra_data": {
                        "description": "CPU usage above 90% for extended period"
                    },
                },
                {
                    "name": "Critical CPU Usage",
                    "condition": "cpu_percent > 95",
                    "severity": "critical",
                    "enabled": True,
                    "extra_data": {"description": "CPU usage critically high"},
                },
                {
                    "name": "High Memory Usage",
                    "condition": "memory_percent > 90",
                    "severity": "warning",
                    "enabled": True,
                    "extra_data": {"description": "Memory usage above 90%"},
                },
                {
                    "name": "Low Disk Space",
                    "condition": "disk_percent > 95",
                    "severity": "critical",
                    "enabled": True,
                    "extra_data": {"description": "Disk space critically low"},
                },
                {
                    "name": "Redis Unavailable",
                    "condition": "redis_healthy == 0",
                    "severity": "warning",
                    "enabled": True,
                    "extra_data": {"description": "Redis cache unavailable"},
                },
                {
                    "name": "Snowflake Connection Failed",
                    "condition": "snowflake_healthy == 0",
                    "severity": "critical",
                    "enabled": True,
                    "extra_data": {
                        "description": "Cannot connect to Snowflake database"
                    },
                },
            ]

            for rule_data in default_rules:
                rule = AlertRule(**rule_data)
                session.add(rule)

            session.commit()

        logger.info(f"✅ Initialized {len(default_rules)} default alert rules")

    except Exception as e:
        logger.error(f"Error initializing default rules: {e}", exc_info=True)


def _check_redis_health() -> bool:
    """Check if Redis is available."""
    try:
        import redis

        redis_client = redis.Redis(
            host=os.getenv("REDIS_HOST", "localhost"),
            port=int(os.getenv("REDIS_PORT", "6379")),
            socket_connect_timeout=1,
        )
        redis_client.ping()
        return True
    except (redis.ConnectionError, redis.TimeoutError, Exception) as e:
        logger.debug(f"Redis health check failed: {e}")
        return False


def _check_snowflake_health() -> bool:
    """Check if Snowflake connection is available."""
    try:
        import snowflake.connector

        from analysis.shared.connections import get_snowflake_connection_params

        params = get_snowflake_connection_params()

        # Override timeouts for quick health check (params already includes them)
        params["network_timeout"] = 5  # Short timeout for health check
        params["login_timeout"] = 5

        # Quick connection test with short timeout
        conn = snowflake.connector.connect(**params)
        conn.cursor().execute("SELECT 1")
        conn.close()
        return True
    except ImportError as e:
        logger.warning(f"⚠️  Snowflake connector not installed: {e}")
        return False
    except Exception as e:
        logger.warning(f"⚠️  Snowflake health check failed: {e}")
        return False
