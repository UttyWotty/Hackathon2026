"""
CT Deviation Core Package.

Exports data loading and deviation calculation functions.
"""

from .data_loader import (
    create_snowflake_connector,
    create_snowpark_session,
    fetch_ct_deviation_data,
    validate_ct_data,
)
from .deviation_calculator import (
    calculate_deviation_metrics,
    calculate_rolling_deviation,
    detect_statistical_outliers,
    generate_summary_statistics,
)

__all__ = [
    "create_snowpark_session",
    "create_snowflake_connector",
    "fetch_ct_deviation_data",
    "validate_ct_data",
    "calculate_deviation_metrics",
    "detect_statistical_outliers",
    "calculate_rolling_deviation",
    "generate_summary_statistics",
]
