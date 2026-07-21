"""Configuration module for the ANA_SHOT_MADE pipeline re-exporting shared infrastructure and pipeline-specific constants.
Re-exports Snowflake session factories and shared constants from the shared pipeline configuration.
Defines SESSION_GAP_HOURS as the pipeline-specific inactivity threshold for session detection.
"""

from analysis.shared.constants import SessionDetection

from ..shared_config import (
    CHUNK_SIZE,
    OVERLAP_DAYS,
    get_database_schema,
    get_snowflake_connector,
    get_snowflake_session,
    setup_pipeline_logging,
)

SESSION_GAP_HOURS: int = SessionDetection.SESSION_GAP_HOURS

DATABASE_NAME, SCHEMA_NAME = get_database_schema()


def setup_logging():
    """Configure logging for ANA_SHOT_MADE pipeline."""
    return setup_pipeline_logging("ANA_SHOT_MADE")


__all__ = [
    "get_snowflake_session",
    "get_snowflake_connector",
    "setup_logging",
    "DATABASE_NAME",
    "SCHEMA_NAME",
    "OVERLAP_DAYS",
    "CHUNK_SIZE",
    "SESSION_GAP_HOURS",
]
