"""
Shared Utilities Package
========================

Centralized utilities for all manufacturing analysis modules.
Provides consistent database connections, logging, error handling,
data validation, file operations, and constants.

Author: Utku Gulbardak
Date: 2025-10-28

Usage:
    from analysis.shared import setup_module_logger, create_snowflake_connection
    from analysis.shared import validate_dataframe, generate_filepath
    from analysis.shared import AnalysisThresholds, ColumnNames

Example:
    >>> from analysis.shared import (
    ...     setup_module_logger,
    ...     create_snowflake_connection,
    ...     validate_machine_ids,
    ...     generate_filepath
    ... )
    >>>
    >>> logger = setup_module_logger("MyAnalysis")
    >>> conn = create_snowflake_connection()
    >>> equipment = validate_machine_ids("MX-7110")
    >>> output_path = generate_filepath("output", "report", "xlsx")
"""

# Connections
from .connections import (
    SnowflakeConnectionError,
    create_snowflake_connection,
    get_schema_name,
    get_snowflake_connection_params,
    get_snowflake_connection_params_with_schema,
    load_private_key,
    test_snowflake_connection,
)

# Constants
from .constants import (
    AnalysisConfig,
    AnalysisStatus,
    AnalysisThresholds,
    ColumnNames,
    DatabaseSchemas,
    DatabaseTables,
    EquipmentStatus,
    FilePaths,
    ReportConfig,
    SessionDetection,
    ShiftBoundaries,
    SQLTemplates,
    TimeConstants,
)

# Data Validation
from .data_validation import (
    check_data_quality,
    validate_dataframe,
    validate_date_range,
    validate_machine_ids,
    validate_numeric_parameter,
    validate_schema,
)

# Error Handling
from .error_handling import (
    AnalysisError,
    ConfigurationError,
    DataNotFoundError,
    DataValidationError,
    ProcessingError,
    ReportGenerationError,
    graceful_degradation,
    handle_analysis_error,
    log_and_raise,
    retry_on_failure,
    safe_execute,
    validate_or_raise,
)

# File Operations
from .file_operations import (
    clean_filename,
    ensure_directory,
    file_exists,
    generate_filename,
    generate_filepath,
    get_absolute_path,
    get_file_size_mb,
    get_output_dir,
    get_project_root,
    list_files_by_extension,
    safe_read_json,
    safe_write_json,
    temporary_file,
)

# Logging
from .logging import (
    get_logger,
    log_analysis_complete,
    log_analysis_start,
    log_dataframe_info,
    log_execution_time,
    setup_module_logger,
)

# Version information
__version__ = "1.0.0"
__author__ = "Utku Gulbardak"
__date__ = "2025-10-28"


# Define what gets exported with "from analysis.shared import *"
__all__ = [
    # Connections
    "SnowflakeConnectionError",
    "load_private_key",
    "get_snowflake_connection_params",
    "get_snowflake_connection_params_with_schema",
    "create_snowflake_connection",
    "test_snowflake_connection",
    "get_schema_name",
    # Logging
    "setup_module_logger",
    "get_logger",
    "log_execution_time",
    "log_dataframe_info",
    "log_analysis_start",
    "log_analysis_complete",
    # Error Handling
    "AnalysisError",
    "DataValidationError",
    "DataNotFoundError",
    "ConfigurationError",
    "ProcessingError",
    "ReportGenerationError",
    "retry_on_failure",
    "handle_analysis_error",
    "safe_execute",
    "validate_or_raise",
    "log_and_raise",
    "graceful_degradation",
    # Data Validation
    "validate_dataframe",
    "validate_machine_ids",
    "validate_date_range",
    "validate_numeric_parameter",
    "check_data_quality",
    "validate_schema",
    # File Operations
    "ensure_directory",
    "generate_filename",
    "generate_filepath",
    "safe_write_json",
    "safe_read_json",
    "temporary_file",
    "get_file_size_mb",
    "file_exists",
    "clean_filename",
    "get_absolute_path",
    "list_files_by_extension",
    # Constants
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


# Module-level convenience functions
def get_version() -> str:
    """Get the version of the shared utilities package."""
    return __version__


def list_available_utilities() -> dict:
    """List all available utilities by category."""
    return {
        "connections": [
            "create_snowflake_connection",
            "get_snowflake_connection_params",
            "test_snowflake_connection",
        ],
        "logging": [
            "setup_module_logger",
            "log_execution_time",
            "log_dataframe_info",
        ],
        "error_handling": [
            "retry_on_failure",
            "handle_analysis_error",
            "safe_execute",
        ],
        "data_validation": [
            "validate_dataframe",
            "validate_machine_ids",
            "check_data_quality",
        ],
        "file_operations": [
            "generate_filepath",
            "safe_write_json",
            "ensure_directory",
        ],
    }


# Print helpful message when module is imported
import logging as _logging  # noqa: E402

_logger = _logging.getLogger(__name__)
_logger.debug(f"📦 Loaded analysis.shared utilities v{__version__}")
