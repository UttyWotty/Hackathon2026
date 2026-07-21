"""
SQLite-based Audit Logger - Simple, persistent audit logging.

Replaces legacy Snowflake-based AuditLogger with SQLite persistence.
All audit logs are stored in SQLite database for compliance and debugging.

Author: Manufacturing Analytics Team
Date: 2025-11-24
"""

import logging
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def log_audit_event(
    service: str,
    tool_name: str,
    user_id: Optional[str] = None,
    status: str = "success",
    execution_time_ms: Optional[float] = None,
    error_message: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> Optional[int]:
    """
    Log an audit event to SQLite database.

    This is a simple, direct logging function that writes to SQLite.
    Used internally by auth decorators and other services.

    Args:
        service: Service name (e.g., "analytics", "snowflake")
        tool_name: Tool/function name executed
        user_id: User ID (optional)
        status: Status ("success" or "error")
        execution_time_ms: Execution time in milliseconds
        error_message: Error message if status is "error"
        metadata: Additional metadata dictionary
        ip_address: Client IP address (optional)
        user_agent: User agent string (optional)

    Returns:
        int: Log entry ID if successful, None if failed
    """
    try:
        from models.audit import AuditLog
        from models.database import get_session

        with get_session() as session:
            log_entry = AuditLog(
                user_id=user_id or "system",
                service=service,
                tool_name=tool_name,
                status=status,
                execution_time_ms=execution_time_ms,
                error_message=error_message,
                extra_data=metadata or {},
                ip_address=ip_address,
                user_agent=user_agent,
            )

            session.add(log_entry)
            session.commit()

            log_id = log_entry.id

        return log_id

    except Exception as e:
        logger.error(f"Failed to log audit event: {e}", exc_info=True)
        return None
