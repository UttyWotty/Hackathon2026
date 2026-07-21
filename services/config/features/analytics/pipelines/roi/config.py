"""Configuration module for the ROI pipeline re-exporting shared infrastructure and providing pipeline-specific setup.
Re-exports Snowflake session factories and database schema resolution from the shared pipeline configuration.
Pipeline-wide constants OVERLAP_DAYS and CHUNK_SIZE are now defined in shared_config.
"""

from ..shared_config import (
    CHUNK_SIZE,
    OVERLAP_DAYS,
    get_database_schema,
    get_snowflake_connector,
    get_snowflake_session,
    setup_pipeline_logging,
)

DATABASE_NAME, SCHEMA_NAME = get_database_schema()


def setup_logging():
    """Configure logging for ROI pipeline."""
    return setup_pipeline_logging("ROI")


__all__ = [
    "get_snowflake_session",
    "get_snowflake_connector",
    "setup_logging",
    "DATABASE_NAME",
    "SCHEMA_NAME",
    "OVERLAP_DAYS",
    "CHUNK_SIZE",
]
