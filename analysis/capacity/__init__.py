"""
Capacity Analysis Module

Comprehensive capacity and OEE (Overall Equipment Effectiveness) analysis
with multi-target scenarios (50%-100% OEE).

This module provides:
- Session-based OEE calculations
- Availability, Performance, Quality breakdown
- Performance Loss tracking (can be negative for overperformance)
- Multi-cavity mold support
- Excel reports with multiple OEE scenarios
- Interactive HTML dashboards
- Plotly visualizations

Author: Utku Gulbardak
Date: 2025-10-27
"""

# Import core data functions
# Import API entry point
from .api import run_analysis_api
from .core import (
    add_shot_diffs,
    build_session_metrics,
    compute_session_metrics,
    fetch_available_equipment_codes,
    fetch_available_suppliers,
    fetch_equipment_data,
    filter_sessions_by_shot_count,
    get_cavity_count,
    get_schema_name,
    init_env,
    snowflake_connect,
)

# Import config
from .models.config import (
    DEFAULT_END_DATE,
    DEFAULT_EQUIPMENT_CODE,
    DEFAULT_OEE_TARGETS,
    DEFAULT_START_DATE,
    DEFAULT_SUPPLIER_NAME,
    EQUIPMENT_CAVITY_MAPPING,
    CapacityConfig,
)

# Import reporting functions
from .reporting import (
    create_multi_oee_excel,
    generate_formulas_doc_daily,
    generate_sales_doc_daily,
    make_combined_oee_visual,
    make_daily_visual,
    make_oee_visual,
    make_optimal_output_visual,
)

__all__ = [
    # Core data functions
    "init_env",
    "snowflake_connect",
    "get_schema_name",
    "fetch_available_suppliers",
    "fetch_available_equipment_codes",
    "fetch_equipment_data",
    "add_shot_diffs",
    "get_cavity_count",
    "filter_sessions_by_shot_count",
    "compute_session_metrics",
    "build_session_metrics",
    # Config
    "CapacityConfig",
    "DEFAULT_EQUIPMENT_CODE",
    "DEFAULT_SUPPLIER_NAME",
    "DEFAULT_START_DATE",
    "DEFAULT_END_DATE",
    "DEFAULT_OEE_TARGETS",
    "EQUIPMENT_CAVITY_MAPPING",
    # Reporting
    "make_daily_visual",
    "make_oee_visual",
    "make_combined_oee_visual",
    "make_optimal_output_visual",
    "generate_sales_doc_daily",
    "generate_formulas_doc_daily",
    "create_multi_oee_excel",
    # API
    "run_analysis_api",
]

__version__ = "2.0.0"
