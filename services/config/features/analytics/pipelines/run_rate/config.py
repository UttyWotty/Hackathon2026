"""Configuration module for the RUNRATE pipeline re-exporting shared infrastructure and pipeline-specific constants.
Re-exports Snowflake session factories and shared constants from the shared pipeline configuration.
Defines pipeline-specific constants for session gaps, stop thresholds, and mode CT precision.
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
STOP_THRESHOLD: float = SessionDetection.STOP_DEVIATION_THRESHOLD
MODE_CT_DECIMALS: int = SessionDetection.MODE_CT_DECIMALS
MAX_CT_THRESHOLD: float = SessionDetection.HARD_STOP_CT
GAP_TIME_TOLERANCE: float = SessionDetection.GAP_TIME_TOLERANCE_SECONDS

DATABASE_NAME, SCHEMA_NAME = get_database_schema()


def setup_logging():
    """Configure logging for RUNRATE pipeline."""
    return setup_pipeline_logging("RUNRATE")


__all__ = [
    "get_snowflake_session",
    "get_snowflake_connector",
    "setup_logging",
    "DATABASE_NAME",
    "SCHEMA_NAME",
    "SESSION_GAP_HOURS",
    "STOP_THRESHOLD",
    "MODE_CT_DECIMALS",
    "CHUNK_SIZE",
    "OVERLAP_DAYS",
    "MAX_CT_THRESHOLD",
    "GAP_TIME_TOLERANCE",
]
