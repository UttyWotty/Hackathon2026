"""
Database models for persistent storage.

Uses SQLAlchemy ORM with SQLite backend for:
- Scheduled jobs
- Audit logs
- Monitoring metrics
"""

from .audit import AuditLog
from .database import Base, DatabaseInitError, engine, get_session, init_database
from .decision_trail import DecisionRun, DecisionStep
from .email import EmailHistory, EmailQueue
from .monitoring import AlertHistory, AlertRule, MetricRecord
from .scheduler import JobExecutionHistory, ScheduledJob

__all__ = [
    "Base",
    "engine",
    "get_session",
    "init_database",
    "DatabaseInitError",
    "ScheduledJob",
    "JobExecutionHistory",
    "AuditLog",
    "MetricRecord",
    "AlertRule",
    "AlertHistory",
    "EmailQueue",
    "EmailHistory",
    "DecisionRun",
    "DecisionStep",
]
