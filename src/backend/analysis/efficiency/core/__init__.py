"""
Duration Efficiency Core Package.

Exports data loading, efficiency calculation, and supplier benchmarking functions.
"""

from .target_staleness import detect_stale_baselines
from .data_loader import (
    create_snowflake_connector,
    create_snowpark_session,
    fetch_efficiency_data,
    prepare_efficiency_data,
)
from .efficiency_calculator import (
    aggregate_per_tool,
    calculate_confidence_intervals,
    calculate_duration_efficiency,
    generate_efficiency_summary,
    normalize_efficiency_scores,
)
from .operator_benchmarking import (
    benchmark_operators,
    detect_production_sessions,
    detect_shift_patterns,
    generate_operator_summary,
)
from .shift_detector import detect_shift_boundaries, detect_shifts_per_supplier
from .shift_performance import analyze_all_equipment_shifts, analyze_equipment_shifts
from .supplier_benchmarking import (
    assign_supplier_tiers,
    benchmark_suppliers,
    calculate_tool_consistency,
    generate_supplier_summary,
    get_supplier_comparison,
    rank_suppliers,
)
from .tool_comparison import compare_tools_by_target_duration
from .tool_comparison_windowed import compare_tools_windowed

__all__ = [
    # Data Loader
    "create_snowpark_session",
    "create_snowflake_connector",
    "fetch_efficiency_data",
    "prepare_efficiency_data",
    # Efficiency Calculator
    "calculate_duration_efficiency",
    "aggregate_per_tool",
    "calculate_confidence_intervals",
    "normalize_efficiency_scores",
    "generate_efficiency_summary",
    # Supplier Benchmarking
    "benchmark_suppliers",
    "calculate_tool_consistency",
    "rank_suppliers",
    "assign_supplier_tiers",
    "generate_supplier_summary",
    "get_supplier_comparison",
    # Operator Benchmarking
    "benchmark_operators",
    "detect_production_sessions",
    "detect_shift_patterns",
    "generate_operator_summary",
    # Shift Performance
    "analyze_all_equipment_shifts",
    "analyze_equipment_shifts",
    # Tool Comparison
    "compare_tools_by_target_duration",
    "compare_tools_windowed",
    "detect_stale_baselines",
    "detect_shift_boundaries",
    "detect_shifts_per_supplier",
]
