"""
Audit database models.

Stores audit logs for compliance and tracking across server restarts.
"""

from datetime import datetime
from typing import Any, Dict

from sqlalchemy import (  # type: ignore[import-untyped]
    JSON,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)

from .database import Base


class AuditLog(Base):
    """
    Audit log model.

    Stores all API calls and tool executions for compliance and debugging.
    """

    __tablename__ = "audit_logs"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Timestamp
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)

    # Request information
    user_id = Column(String(100), nullable=True, index=True)
    service = Column(String(100), nullable=False, index=True)
    tool_name = Column(String(100), nullable=False, index=True)

    # Execution details
    status = Column(String(50), nullable=False, index=True)  # success, error
    execution_time_ms = Column(Float, nullable=True)

    # Error tracking
    error_message = Column(Text, nullable=True)
    error_type = Column(String(100), nullable=True)

    # Additional context
    extra_data = Column(
        JSON, nullable=True
    )  # Additional data (arguments, results, etc.)
    ip_address = Column(String(45), nullable=True)  # IPv4 or IPv6
    user_agent = Column(String(500), nullable=True)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() if self.timestamp else None,
            "user_id": self.user_id,
            "service": self.service,
            "tool_name": self.tool_name,
            "status": self.status,
            "execution_time_ms": self.execution_time_ms,
            "error_message": self.error_message,
            "error_type": self.error_type,
            "extra_data": self.extra_data,
            "ip_address": self.ip_address,
            "user_agent": self.user_agent,
        }

    def __repr__(self):
        return f"<AuditLog(id={self.id}, service={self.service}, tool={self.tool_name}, status={self.status})>"
