"""
Monitoring database models.

Stores metrics, alerts, and system health data across server restarts.
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)

from .database import Base


class MetricRecord(Base):
    """
    Metric record model.

    Stores time-series metrics for system monitoring and trend analysis.
    """

    __tablename__ = "metrics"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Metric identification
    metric_type = Column(
        String(100), nullable=False, index=True
    )  # cpu_percent, memory_percent, etc.
    metric_name = Column(String(100), nullable=True)  # Optional descriptive name

    # Metric value
    metric_value = Column(Float, nullable=False)

    # Additional context
    extra_data = Column(JSON, nullable=True)  # Additional metric details
    source = Column(
        String(100), nullable=True
    )  # Source of metric (system, application, etc.)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "metric_type": self.metric_type,
            "metric_name": self.metric_name,
            "metric_value": self.metric_value,
            "extra_data": self.extra_data,
            "source": self.source,
        }

    def __repr__(self):
        return f"<MetricRecord(type={self.metric_type}, value={self.metric_value})>"


class AlertRule(Base):
    """
    Alert rule model.

    Stores configuration for automated alert rules.
    """

    __tablename__ = "alert_rules"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Rule configuration
    name = Column(String(200), nullable=False, unique=True, index=True)
    condition = Column(String(500), nullable=False)  # Condition expression
    severity = Column(
        String(50), default="warning", nullable=False
    )  # info, warning, error, critical
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # Timestamps
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Execution tracking
    triggered_count = Column(Integer, default=0, nullable=False)
    last_triggered = Column(DateTime, nullable=True)

    # Additional configuration
    extra_data = Column(JSON, nullable=True)  # Alert channels, thresholds, etc.

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "condition": self.condition,
            "severity": self.severity,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "triggered_count": self.triggered_count,
            "last_triggered": (
                self.last_triggered.isoformat() if self.last_triggered else None
            ),
            "extra_data": self.extra_data,
        }

    def __repr__(self):
        return f"<AlertRule(name={self.name}, enabled={self.enabled})>"


class AlertHistory(Base):
    """
    Alert history model.

    Stores history of triggered alerts for review and analysis.
    """

    __tablename__ = "alert_history"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Alert details
    title = Column(String(200), nullable=False)
    message = Column(Text, nullable=False)
    severity = Column(String(50), nullable=False, index=True)

    # Context
    rule_id = Column(
        Integer, nullable=True
    )  # Reference to alert rule if triggered by rule
    extra_data = Column(JSON, nullable=True)

    # Status
    acknowledged = Column(Boolean, default=False, nullable=False)
    acknowledged_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(String(100), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "title": self.title,
            "message": self.message,
            "severity": self.severity,
            "rule_id": self.rule_id,
            "extra_data": self.extra_data,
            "acknowledged": self.acknowledged,
            "acknowledged_at": (
                self.acknowledged_at.isoformat() if self.acknowledged_at else None
            ),
            "acknowledged_by": self.acknowledged_by,
        }

    def __repr__(self):
        return f"<AlertHistory(title={self.title}, severity={self.severity})>"
