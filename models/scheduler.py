"""
Scheduler database models.

Stores scheduled jobs with persistent state across server restarts.
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Text,
)

from .database import Base


class ScheduledJob(Base):
    """
    Scheduled job model.

    Stores configuration and state for recurring and one-time jobs.
    """

    __tablename__ = "scheduled_jobs"

    # Primary key
    id = Column(String(36), primary_key=True)  # UUID

    # Job configuration
    name = Column(String(200), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)
    arguments = Column(JSON, nullable=True)  # JSON dict of tool arguments
    schedule = Column(String(100), nullable=False)  # Cron or interval
    enabled = Column(Boolean, default=True, nullable=False, index=True)

    # Execution state
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)
    last_run = Column(DateTime, nullable=True)
    next_run = Column(DateTime, nullable=True)
    run_count = Column(Integer, default=0, nullable=False)

    # Status tracking
    status = Column(
        String(50), default="scheduled", nullable=False
    )  # scheduled, running, paused, error
    last_result = Column(Text, nullable=True)  # Last execution result
    error_count = Column(Integer, default=0, nullable=False)
    last_error = Column(Text, nullable=True)

    # Retry configuration
    max_retries = Column(
        Integer, default=3, nullable=False
    )  # Max retry attempts per execution
    retry_count = Column(Integer, default=0, nullable=False)  # Current retry attempt
    retry_backoff = Column(
        Integer, default=60, nullable=False
    )  # Seconds between retries

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "name": self.name,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "schedule": self.schedule,
            "enabled": self.enabled,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "run_count": self.run_count,
            "status": self.status,
            "error_count": self.error_count,
            "last_error": self.last_error,
            "max_retries": self.max_retries,
            "retry_count": self.retry_count,
            "retry_backoff": self.retry_backoff,
        }

    def __repr__(self):
        return f"<ScheduledJob(id={self.id}, name={self.name}, enabled={self.enabled})>"


class JobExecutionHistory(Base):
    """
    Job execution history model for full audit trail.

    Stores complete execution history for all scheduled jobs, including full results.
    Maintains separation: job configuration in ScheduledJob, execution history here.
    """

    __tablename__ = "job_execution_history"

    # Primary key
    id = Column(String(36), primary_key=True)  # UUID

    # Job reference
    job_id = Column(
        String(36), nullable=False, index=True
    )  # References ScheduledJob.id
    job_name = Column(String(200), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)

    # Execution details
    started_at = Column(DateTime, nullable=False, index=True)
    completed_at = Column(DateTime, nullable=True)
    execution_time_ms = Column(Integer, nullable=True)

    # Status
    status = Column(String(50), nullable=False, index=True)  # success, error, cancelled
    error_message = Column(Text, nullable=True)

    # Full results (not truncated)
    result_data = Column(JSON, nullable=True)  # Full result JSON
    result_summary = Column(Text, nullable=True)  # Human-readable summary

    # Arguments used
    arguments = Column(JSON, nullable=True)  # Arguments passed to tool

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "job_id": self.job_id,
            "job_name": self.job_name,
            "tool_name": self.tool_name,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": (
                self.completed_at.isoformat() if self.completed_at else None
            ),
            "execution_time_ms": self.execution_time_ms,
            "status": self.status,
            "error_message": self.error_message,
            "result_data": self.result_data,
            "result_summary": self.result_summary,
            "arguments": self.arguments,
        }

    def __repr__(self):
        return f"<JobExecutionHistory(id={self.id}, job={self.job_name}, status={self.status})>"
