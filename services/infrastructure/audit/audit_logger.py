"""
DEPRECATED: Legacy Snowflake-based Audit Logger.

This module is DEPRECATED and kept for backward compatibility only.
The system now uses SQLite-based audit logging via:
- services/infrastructure/audit/sqlite_logger.py (for direct logging)
- routers/audit_router.py (for API endpoints)

All new code should use sqlite_logger.log_audit_event() instead.

This file will be removed in a future version.

Author: Utku Gulbardak
Date: 2025-11-12 (Deprecated: 2025-11-24)
"""

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

logger = logging.getLogger(__name__)


class AuditLogger:
    """
    Audit Logger for MCP Server Activity.

    Logs all MCP calls to Snowflake for compliance and debugging.
    Tracks user activity, performance metrics, and costs.
    """

    def __init__(self, snowflake_session: Optional[Any] = None, enabled: bool = True):
        """
        Initialize Audit Logger.

        Args:
            snowflake_session: Optional Snowpark session for logging
            enabled: Whether audit logging is enabled
        """
        self.session = snowflake_session
        self.enabled = enabled
        self.table_name = "MCP_AUDIT_LOG"
        self.database = os.getenv("SNOWFLAKE_DATABASE", "COTEX")
        self.schema = os.getenv("SNOWFLAKE_SCHEMA", "PUBLIC")

        # In-memory buffer for batch writing
        self._buffer: List[Dict] = []
        self._buffer_size = int(os.getenv("AUDIT_BUFFER_SIZE", "100"))

        if self.enabled:
            self._ensure_table_exists()
            logger.info("✅ Audit Logger initialized")
        else:
            logger.info("ℹ️  Audit Logger disabled")

    def log_event(
        self,
        mcp_server: str,
        tool_name: str,
        arguments: Dict[str, Any],
        status: str,
        user_id: Optional[str] = None,
        email: Optional[str] = None,
        role: Optional[str] = None,
        execution_time_ms: Optional[float] = None,
        rows_returned: Optional[int] = None,
        error_message: Optional[str] = None,
        snowflake_credits: Optional[float] = None,
        metadata: Optional[Dict] = None,
    ) -> str:
        """
        Log an MCP event.

        Args:
            mcp_server: MCP server name (e.g., "analytics-mcp")
            tool_name: Tool name executed
            arguments: Tool arguments (will be JSON serialized)
            status: Status ("success", "error", "timeout")
            user_id: User who triggered the event
            email: User email
            role: User role
            execution_time_ms: Execution time in milliseconds
            rows_returned: Number of rows returned
            error_message: Error message if status is "error"
            snowflake_credits: Estimated Snowflake credits used
            metadata: Additional metadata

        Returns:
            str: Event ID
        """
        if not self.enabled:
            return ""

        event_id = str(uuid4())
        timestamp = datetime.now()

        # Create audit record
        record = {
            "event_id": event_id,
            "timestamp": timestamp.isoformat(),
            "mcp_server": mcp_server,
            "tool_name": tool_name,
            "arguments": self._sanitize_arguments(arguments),
            "status": status,
            "user_id": user_id or "anonymous",
            "email": email or "unknown",
            "role": role or "unknown",
            "execution_time_ms": execution_time_ms,
            "rows_returned": rows_returned,
            "error_message": error_message,
            "snowflake_credits": snowflake_credits,
            "metadata": metadata or {},
        }

        # Add to buffer
        self._buffer.append(record)

        # Flush if buffer is full
        if len(self._buffer) >= self._buffer_size:
            self._flush_buffer()

        return event_id

    def _sanitize_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize arguments to remove sensitive data.

        Args:
            arguments: Raw arguments

        Returns:
            dict: Sanitized arguments
        """
        # Copy to avoid modifying original
        sanitized = arguments.copy()

        # Remove sensitive fields
        sensitive_keys = ["password", "token", "api_key", "secret", "credential"]
        for key in list(sanitized.keys()):
            if any(sensitive in key.lower() for sensitive in sensitive_keys):
                sanitized[key] = "***REDACTED***"

        # Truncate large strings
        for key, value in sanitized.items():
            if isinstance(value, str) and len(value) > 1000:
                sanitized[key] = value[:1000] + "...[truncated]"

        return sanitized

    def _flush_buffer(self):
        """Flush buffer to Snowflake."""
        if not self._buffer:
            return

        if not self.session:
            logger.warning("⚠️  Snowflake session not available, discarding audit logs")
            self._buffer.clear()
            return

        try:
            # Convert to DataFrame
            import pandas as pd

            df = pd.DataFrame(self._buffer)

            # Convert dict columns to JSON strings
            for col in ["arguments", "metadata"]:
                if col in df.columns:
                    df[col] = df[col].apply(lambda x: json.dumps(x) if x else "{}")

            # Write to Snowflake
            from snowflake.connector.pandas_tools import write_pandas

            # Get connection from session
            conn = self.session._conn if hasattr(self.session, "_conn") else None
            if conn:
                write_pandas(
                    conn=conn,
                    df=df,
                    table_name=self.table_name,
                    schema=self.schema,
                    database=self.database,
                    auto_create_table=False,
                    overwrite=False,
                )
                logger.info(
                    f"✅ Flushed {len(self._buffer)} audit records to Snowflake"
                )
            else:
                logger.warning("⚠️  Could not get connection from session")

        except Exception as e:
            logger.error(f"❌ Failed to flush audit logs: {e}")

        finally:
            self._buffer.clear()

    def _ensure_table_exists(self):
        """Create audit log table if it doesn't exist."""
        if not self.session:
            logger.warning(
                "⚠️  Snowflake session not available, skipping table creation"
            )
            return

        try:
            # Check if table exists
            check_query = f"""
            SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = '{self.schema}' 
            AND TABLE_NAME = '{self.table_name}'
            """

            result = self.session.sql(check_query).collect()
            if result[0][0] > 0:
                logger.info(f"ℹ️  Audit table {self.table_name} already exists")
                return

            # Create table
            create_query = f"""
            CREATE TABLE {self.database}.{self.schema}.{self.table_name} (
                EVENT_ID STRING,
                TIMESTAMP TIMESTAMP,
                MCP_SERVER STRING,
                TOOL_NAME STRING,
                ARGUMENTS STRING,  -- JSON
                STATUS STRING,
                USER_ID STRING,
                EMAIL STRING,
                ROLE STRING,
                EXECUTION_TIME_MS FLOAT,
                ROWS_RETURNED NUMBER,
                ERROR_MESSAGE STRING,
                SNOWFLAKE_CREDITS FLOAT,
                METADATA STRING,  -- JSON
                CREATED_AT TIMESTAMP DEFAULT CURRENT_TIMESTAMP()
            )
            """

            self.session.sql(create_query).collect()
            logger.info(
                f"✅ Created audit table: {self.database}.{self.schema}.{self.table_name}"
            )

        except Exception as e:
            logger.error(f"❌ Failed to ensure audit table exists: {e}")

    def query_logs(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        user_id: Optional[str] = None,
        mcp_server: Optional[str] = None,
        tool_name: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 1000,
    ) -> List[Dict]:
        """
        Query audit logs.

        Args:
            start_date: Filter by start date (YYYY-MM-DD)
            end_date: Filter by end date (YYYY-MM-DD)
            user_id: Filter by user ID
            mcp_server: Filter by MCP server
            tool_name: Filter by tool name
            status: Filter by status
            limit: Max results to return

        Returns:
            list: Audit log records
        """
        if not self.enabled or not self.session:
            return []

        # Flush buffer first
        self._flush_buffer()

        # Build query with proper sanitization
        where_clauses = []

        # Validate and sanitize inputs to prevent SQL injection
        if start_date:
            # Validate date format (YYYY-MM-DD)
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", start_date):
                raise ValueError(
                    f"Invalid date format: {start_date}. Expected YYYY-MM-DD"
                )
            # Escape single quotes
            safe_start_date = start_date.replace("'", "''")
            where_clauses.append(f"DATE(TIMESTAMP) >= '{safe_start_date}'")

        if end_date:
            # Validate date format
            if not re.match(r"^\d{4}-\d{2}-\d{2}$", end_date):
                raise ValueError(
                    f"Invalid date format: {end_date}. Expected YYYY-MM-DD"
                )
            safe_end_date = end_date.replace("'", "''")
            where_clauses.append(f"DATE(TIMESTAMP) <= '{safe_end_date}'")

        if user_id:
            # Sanitize user_id (alphanumeric, underscore, hyphen only)
            if not re.match(r"^[a-zA-Z0-9_-]+$", user_id):
                raise ValueError(f"Invalid user_id format: {user_id}")
            safe_user_id = user_id.replace("'", "''")
            where_clauses.append(f"USER_ID = '{safe_user_id}'")

        if mcp_server:
            # Sanitize mcp_server
            if not re.match(r"^[a-zA-Z0-9_-]+$", mcp_server):
                raise ValueError(f"Invalid mcp_server format: {mcp_server}")
            safe_mcp_server = mcp_server.replace("'", "''")
            where_clauses.append(f"MCP_SERVER = '{safe_mcp_server}'")

        if tool_name:
            # Sanitize tool_name
            if not re.match(r"^[a-zA-Z0-9_-]+$", tool_name):
                raise ValueError(f"Invalid tool_name format: {tool_name}")
            safe_tool_name = tool_name.replace("'", "''")
            where_clauses.append(f"TOOL_NAME = '{safe_tool_name}'")

        if status:
            # Sanitize status (should be specific values)
            if not re.match(r"^[a-zA-Z0-9_-]+$", status):
                raise ValueError(f"Invalid status format: {status}")
            safe_status = status.replace("'", "''")
            where_clauses.append(f"STATUS = '{safe_status}'")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
        SELECT *
        FROM {self.database}.{self.schema}.{self.table_name}
        WHERE {where_sql}
        ORDER BY TIMESTAMP DESC
        LIMIT {limit}
        """

        try:
            df = self.session.sql(query).to_pandas()
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"❌ Failed to query audit logs: {e}")
            return []

    def get_user_activity(
        self,
        user_id: str,
        days: int = 30,
    ) -> Dict[str, Any]:
        """
        Get user activity summary.

        Args:
            user_id: User ID
            days: Number of days to analyze

        Returns:
            dict: User activity metrics
        """
        if not self.enabled or not self.session:
            return {}

        # Flush buffer first
        self._flush_buffer()

        query = f"""
        SELECT
            COUNT(*) as total_calls,
            COUNT(DISTINCT TOOL_NAME) as unique_tools,
            COUNT(DISTINCT DATE(TIMESTAMP)) as active_days,
            AVG(EXECUTION_TIME_MS) as avg_execution_time_ms,
            SUM(SNOWFLAKE_CREDITS) as total_credits,
            COUNT(CASE WHEN STATUS = 'success' THEN 1 END) as successful_calls,
            COUNT(CASE WHEN STATUS = 'error' THEN 1 END) as failed_calls
        FROM {self.database}.{self.schema}.{self.table_name}
        WHERE USER_ID = '{user_id}'
        AND TIMESTAMP >= DATEADD(day, -{days}, CURRENT_TIMESTAMP())
        """

        try:
            df = self.session.sql(query).to_pandas()
            result = df.to_dict(orient="records")[0] if not df.empty else {}

            # Calculate success rate
            total = result.get("total_calls", 0)
            success = result.get("successful_calls", 0)
            result["success_rate"] = round(
                (success / total * 100) if total > 0 else 0, 2
            )

            return result
        except Exception as e:
            logger.error(f"❌ Failed to get user activity: {e}")
            return {}

    def get_cost_report(
        self,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        group_by: str = "mcp_server",
    ) -> List[Dict]:
        """
        Get cost report by MCP server or user.

        Args:
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            group_by: Group by field ("mcp_server", "user_id", "tool_name")

        Returns:
            list: Cost breakdown
        """
        if not self.enabled or not self.session:
            return []

        # Flush buffer first
        self._flush_buffer()

        where_clauses = []
        if start_date:
            where_clauses.append(f"DATE(TIMESTAMP) >= '{start_date}'")
        if end_date:
            where_clauses.append(f"DATE(TIMESTAMP) <= '{end_date}'")

        where_sql = " AND ".join(where_clauses) if where_clauses else "1=1"

        query = f"""
        SELECT
            {group_by.upper()} as category,
            COUNT(*) as total_calls,
            SUM(SNOWFLAKE_CREDITS) as total_credits,
            AVG(EXECUTION_TIME_MS) as avg_execution_time_ms,
            SUM(ROWS_RETURNED) as total_rows_returned
        FROM {self.database}.{self.schema}.{self.table_name}
        WHERE {where_sql}
        GROUP BY {group_by.upper()}
        ORDER BY total_credits DESC
        """

        try:
            df = self.session.sql(query).to_pandas()
            return df.to_dict(orient="records")
        except Exception as e:
            logger.error(f"❌ Failed to get cost report: {e}")
            return []

    def close(self):
        """Flush buffer and close logger."""
        self._flush_buffer()


# Global audit logger instance
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger(snowflake_session: Optional[Any] = None) -> AuditLogger:
    """
    Get global audit logger instance.

    Args:
        snowflake_session: Optional Snowpark session

    Returns:
        AuditLogger: Global audit logger instance
    """
    global _audit_logger
    if _audit_logger is None:
        # Get Snowflake session if not provided
        if snowflake_session is None:
            try:
                from services.infrastructure.snowflake.session_pool import (
                    get_session_pool,
                )

                pool = get_session_pool()
                snowflake_session = pool.get_session()
            except (ImportError, AttributeError, Exception) as e:
                logger.warning(
                    f"⚠️  Could not get Snowflake session for audit logging: {e}"
                )

        # Check if audit logging is enabled
        enabled = os.getenv("AUDIT_LOGGING_ENABLED", "true").lower() == "true"

        _audit_logger = AuditLogger(
            snowflake_session=snowflake_session,
            enabled=enabled,
        )
    return _audit_logger
