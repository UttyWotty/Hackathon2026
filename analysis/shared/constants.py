"""
Common Constants
===============

Shared constants, enums, and configuration values used across analysis modules.

Author: Utku Gulbardak
Date: 2025-10-28
"""

from enum import Enum

# ============================================================================
# Analysis Thresholds
# ============================================================================


class AnalysisThresholds:
    """Common thresholds for analysis operations."""

    # Cycle time thresholds
    CT_DEVIATION_WARNING = 10.0  # %
    CT_DEVIATION_CRITICAL = 20.0  # %
    MAX_ACCEPTABLE_CT = 999.9  # seconds

    # Efficiency thresholds
    EFFICIENCY_EXCELLENT = 90.0  # %
    EFFICIENCY_GOOD = 80.0  # %
    EFFICIENCY_ACCEPTABLE = 70.0  # %
    EFFICIENCY_POOR = 60.0  # %

    # Downtime thresholds
    STOP_THRESHOLD_SECONDS = 28800  # 8 hours
    STOP_THRESHOLD_MINUTES = 480  # 8 hours

    # Data quality thresholds
    MAX_NULL_PERCENTAGE = 10.0  # %
    MIN_DATA_POINTS = 10  # minimum rows for analysis


class ShiftBoundaries:
    """Manufacturing shift boundary hours (24-hour clock)."""

    DAY_START_HOUR: int = 6  # 06:00 - Day/Morning shift begins
    AFTERNOON_START_HOUR: int = 14  # 14:00 - Afternoon shift begins
    NIGHT_START_HOUR: int = 22  # 22:00 - Night shift begins


class SessionDetection:
    """Thresholds for production session detection and stop classification."""

    SESSION_GAP_HOURS: int = 8  # Hours of inactivity to start new session
    SESSION_GAP_SECONDS: int = 28800  # SESSION_GAP_HOURS * 3600
    STOP_DEVIATION_THRESHOLD: float = 0.05  # +/-5% from mode CT triggers stop
    GAP_TIME_TOLERANCE_SECONDS: float = 2.0  # Gap > CT + this value = stop
    HARD_STOP_CT: float = 999.9  # CT >= this value = hard stop / idle
    MODE_CT_DECIMALS: int = 2  # Rounding precision for mode CT


# ============================================================================
# Equipment Status
# ============================================================================


class EquipmentStatus(Enum):
    """Equipment operational status."""

    ACTIVE = "active"
    IDLE = "idle"
    MAINTENANCE = "maintenance"
    OFFLINE = "offline"
    UNKNOWN = "unknown"


class AnalysisStatus(Enum):
    """Analysis execution status."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


# ============================================================================
# File and Directory Constants
# ============================================================================


class FilePaths:
    """Standard file paths and directories."""

    # Central output directories (relative to manufacturing-api root)
    OUTPUT_DIR = "output"
    LOGS_DIR = "logs"
    REPORTS_DIR = "output/reports"
    DATA_DIR = "data"
    TEMP_DIR = "temp"

    # Module-specific output subdirectories (all under output/)
    ROI_OUTPUT = "output/roi"

    CT_DEVIATION_OUTPUT = "output/ct_deviation"
    CT_EFFICIENCY_OUTPUT = "output/ct_efficiency"
    RCA_OUTPUT = "output/rca"
    TOOLING_EOL_OUTPUT = "output/tooling_eol"

    # File extensions
    EXCEL_EXT = ".xlsx"
    CSV_EXT = ".csv"
    JSON_EXT = ".json"
    HTML_EXT = ".html"
    PDF_EXT = ".pdf"


# ============================================================================
# Database Constants
# ============================================================================


class DatabaseTables:
    """Standard Snowflake table names."""

    MASTER_SHOT_TABLE = "MASTER_SHOT_TABLE"
    PRODUCT = "PRODUCT"
    ANA_SHOT_MADE = "ANA_SHOT_MADE"
    ROI_TABLE = "ROI"
    EQUIPMENT_MASTER = "EQUIPMENT_MASTER"


class DatabaseSchemas:
    """Standard Snowflake schema names."""

    PUBLIC = "PUBLIC"
    NORDPLAST = "NORDPLAST"
    ANALYTICS = "ANALYTICS"


# ============================================================================
# Column Name Constants
# ============================================================================


class ColumnNames:
    """Standard column names across datasets."""

    # Equipment identifiers
    EQUIPMENT_CODE = "EQUIPMENT_CODE"
    MOLD_ID = "MOLD_ID"
    COUNTER_CODE = "COUNTER_CODE"

    # Time columns
    DATE = "DATE"
    TIMESTAMP = "TIMESTAMP"
    LOCAL_SHOT_TIME = "LOCAL_SHOT_TIME"

    # Production metrics
    SHOTS = "SHOTS"
    CYCLE_TIME = "CT"
    APPROVED_CT = "APPROVED_CT"

    # Status columns
    CT_STATUS = "CT_STATUS"
    EQUIPMENT_STATUS = "EQUIPMENT_STATUS"

    # Part information
    PART_ID = (
        "PART_ID"  # Note: Stores part_code (STRING like "218-155"), not numeric ID
    )
    PART_NAME = "PART_NAME"

    # Supplier information
    SUPPLIER_NAME = "SUPPLIER_NAME"
    COMPANY_ID = "COMPANY_ID"


# ============================================================================
# Time Constants
# ============================================================================


class TimeConstants:
    """Time-related constants."""

    # Seconds
    SECONDS_PER_MINUTE = 60
    SECONDS_PER_HOUR = 3600
    SECONDS_PER_DAY = 86400

    # Minutes
    MINUTES_PER_HOUR = 60
    MINUTES_PER_DAY = 1440
    MINUTES_PER_WEEK = 10080

    # Hours
    HOURS_PER_DAY = 24
    HOURS_PER_WEEK = 168

    # Days
    DAYS_PER_WEEK = 7
    DAYS_PER_MONTH = 30  # Average
    DAYS_PER_YEAR = 365


# ============================================================================
# Analysis Configuration
# ============================================================================


class AnalysisConfig:
    """Default configuration for analysis operations."""

    # Date ranges
    DEFAULT_DAYS_BACK = 30
    MAX_DATE_RANGE_DAYS = 365

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2
    RETRY_BACKOFF_MULTIPLIER = 2.0

    # Batch sizes
    BATCH_SIZE_SMALL = 1000
    BATCH_SIZE_MEDIUM = 10000
    BATCH_SIZE_LARGE = 100000

    # Logging
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    LOG_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


# ============================================================================
# Report Configuration
# ============================================================================


class ReportConfig:
    """Configuration for report generation."""

    # Excel formatting
    EXCEL_HEADER_COLOR = "366092"
    EXCEL_HIGHLIGHT_COLOR = "FFC000"
    EXCEL_WARNING_COLOR = "FF0000"

    # Chart sizes
    CHART_WIDTH = 1200
    CHART_HEIGHT = 600
    CHART_DPI = 100

    # HTML styling
    HTML_THEME = "plotly_white"
    HTML_COLOR_SCHEME = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd"]


# ============================================================================
# SQL Query Templates
# ============================================================================


class SQLTemplates:
    """Common SQL query templates."""

    # Basic queries
    COUNT_QUERY = "SELECT COUNT(*) FROM {table}"
    DISTINCT_QUERY = "SELECT DISTINCT {column} FROM {table}"
    DATE_RANGE_QUERY = (
        "SELECT * FROM {table} WHERE {date_col} BETWEEN '{start}' AND '{end}'"
    )

    # Equipment queries
    EQUIPMENT_DATA_QUERY = """
        SELECT * 
        FROM {table}
        WHERE EQUIPMENT_CODE = '{equipment_code}'
        AND {date_col} BETWEEN '{start_date}' AND '{end_date}'
        ORDER BY {date_col}
    """

    # Aggregation queries
    DAILY_AGGREGATION = """
        SELECT 
            DATE_TRUNC('DAY', {date_col}) as DATE,
            COUNT(*) as SHOT_COUNT,
            AVG({metric_col}) as AVG_METRIC
        FROM {table}
        WHERE {date_col} BETWEEN '{start_date}' AND '{end_date}'
        GROUP BY DATE_TRUNC('DAY', {date_col})
        ORDER BY DATE
    """


# Module metadata
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__all__ = [
    # Classes
    "AnalysisThresholds",
    "ShiftBoundaries",
    "SessionDetection",
    "EquipmentStatus",
    "AnalysisStatus",
    "FilePaths",
    "DatabaseTables",
    "DatabaseSchemas",
    "ColumnNames",
    "TimeConstants",
    "AnalysisConfig",
    "ReportConfig",
    "SQLTemplates",
]
