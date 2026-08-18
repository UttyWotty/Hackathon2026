"""Shared Pipeline Configuration
=============================

Common configuration and utilities for all data pipelines.
Uses the centralized Snowflake connection from analysis.shared.connections.
"""

import logging
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from analysis.shared.connections import (
    create_snowflake_connection,
    create_snowpark_session,
    get_schema_name,
)

logger = logging.getLogger(__name__)

# Shared pipeline constants -- used as defaults by base classes and pipeline configs
OVERLAP_DAYS: int = 7
CHUNK_SIZE: int = 500_000


@dataclass
class PipelineConfig:
    """Configuration for pipeline processing."""

    chunk_size_days: int = 3
    max_workers: int = 2
    batch_upload_size: int = 200000
    overlap_days: int = 7
    max_delete_days: int = 14
    max_delete_percentage: float = 0.2
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    schema_name: Optional[str] = None


def setup_pipeline_logging(pipeline_name: str) -> logging.Logger:
    """Configure logging for a specific pipeline.

    Args:
        pipeline_name: Name of the pipeline (e.g., 'MASTER_SHOT', 'ROI')

    Returns:
        Configured logger instance
    """
    pipeline_logger = logging.getLogger(pipeline_name)

    # Use the logger itself as the guard — getLogger() is a true singleton
    # even when shared_config is imported via different paths
    if pipeline_logger.handlers:
        return pipeline_logger

    pipeline_logger.setLevel(logging.INFO)

    # Use absolute path relative to project root so logs are always saved
    # in the same place regardless of the server's working directory
    project_root = os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..")
    )
    log_dir = os.path.join(project_root, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(
        log_dir, f"{pipeline_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    )

    # File handler — append mode so logs survive across calls
    file_handler = logging.FileHandler(log_file, mode="a")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    pipeline_logger.addHandler(file_handler)

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    pipeline_logger.addHandler(console_handler)
    pipeline_logger.propagate = False

    pipeline_logger.info(f"Logging configured for {pipeline_name}")
    return pipeline_logger


def _set_statement_timeout(session_or_conn, timeout: int):
    """Set STATEMENT_TIMEOUT_IN_SECONDS on a Snowpark session or connector connection.

    Prevents queries from using the Snowflake account/warehouse default timeout,
    which can be as low as 300 seconds on some configurations.

    Args:
        session_or_conn: Snowpark session or connector connection
        timeout: Timeout in seconds
    """
    alter_sql = f"ALTER SESSION SET STATEMENT_TIMEOUT_IN_SECONDS = {timeout}"
    try:
        if hasattr(session_or_conn, "sql"):
            # Snowpark session
            session_or_conn.sql(alter_sql).collect()
        else:
            # Connector connection
            cursor = session_or_conn.cursor()
            cursor.execute(alter_sql)
            cursor.close()
        logger.info(f"Statement timeout set to {timeout}s")
    except Exception as e:
        logger.warning(f"Could not set statement timeout: {e}")


def get_snowflake_session(schema: Optional[str] = None):
    """Get Snowflake Snowpark session using shared connection config.

    Sets STATEMENT_TIMEOUT_IN_SECONDS from SNOWFLAKE_STATEMENT_TIMEOUT env var
    (default: 7200s) to prevent premature query timeouts on large datasets.

    Args:
        schema: Optional schema override

    Returns:
        Snowpark Session
    """
    session = create_snowpark_session(schema=schema)
    timeout = int(os.getenv("SNOWFLAKE_STATEMENT_TIMEOUT", "7200"))
    _set_statement_timeout(session, timeout)
    return session


def get_snowflake_connector(schema: Optional[str] = None):
    """Get Snowflake connector connection using shared connection config.

    Sets STATEMENT_TIMEOUT_IN_SECONDS from SNOWFLAKE_STATEMENT_TIMEOUT env var
    (default: 7200s) to prevent premature query timeouts on large datasets.

    Args:
        schema: Optional schema override

    Returns:
        Snowflake connector connection
    """
    conn = create_snowflake_connection(schema=schema)
    timeout = int(os.getenv("SNOWFLAKE_STATEMENT_TIMEOUT", "7200"))
    _set_statement_timeout(conn, timeout)
    return conn


def get_database_schema() -> tuple:
    """Get database and schema names from environment.

    Returns:
        Tuple of (database_name, schema_name)
    """
    database = os.getenv("SNOWFLAKE_DATABASE", "MMS")
    schema = get_schema_name()
    return database, schema
