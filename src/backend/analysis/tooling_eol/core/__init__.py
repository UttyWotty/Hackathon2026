"""
Tooling EOL Core Package.

Exports core functionality for tooling end-of-life prediction.
"""

from .data_loader import (
    create_snowpark_session,
    ensure_time_column,
    get_db_schema,
    normalize_columns,
    read_shot_data,
    read_maintenance_events,
    read_tool_table,
)
from .eol_predictor import (
    calculate_confidence_from_history,
    predict_end_of_life,
    predict_end_of_life_for_mold,
)
from .rate_calculator import (
    calculate_weekly_rate,
    count_active_months,
    detect_seasonality,
)
from .utilization_analyzer import (
    categorize_utilization,
    compute_capacity_and_utilization,
)

__all__ = [
    # Data loading
    "create_snowpark_session",
    "get_db_schema",
    "read_shot_data",
    "read_maintenance_events",
    "read_tool_table",
    "normalize_columns",
    "ensure_time_column",
    # Rate calculation
    "calculate_weekly_rate",
    "detect_seasonality",
    "count_active_months",
    # Utilization analysis
    "compute_capacity_and_utilization",
    "categorize_utilization",
    # EOL prediction
    "predict_end_of_life",
    "predict_end_of_life_for_mold",
    "calculate_confidence_from_history",
]
