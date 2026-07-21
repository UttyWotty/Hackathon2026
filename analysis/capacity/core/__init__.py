"""
Core business logic for Capacity Analysis.

Exposes key functions for:
- Data loading from Snowflake
- Data preprocessing and session splitting
- Metrics calculation and OEE analysis
"""

from .data_loader import (
    fetch_available_equipment_codes,
    fetch_available_suppliers,
    fetch_equipment_data,
    get_schema_name,
    init_env,
    snowflake_connect,
)
from .data_processor import (
    add_shot_diffs,
    filter_sessions_by_shot_count,
    get_cavity_count,
)
from .metrics import build_session_metrics, compute_session_metrics

__all__ = [
    # Data loading
    "init_env",
    "snowflake_connect",
    "get_schema_name",
    "fetch_available_suppliers",
    "fetch_available_equipment_codes",
    "fetch_equipment_data",
    # Data processing
    "add_shot_diffs",
    "get_cavity_count",
    "filter_sessions_by_shot_count",
    # Metrics calculation
    "compute_session_metrics",
    "build_session_metrics",
]
