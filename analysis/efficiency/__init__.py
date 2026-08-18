"""
Duration Efficiency Analysis Module
======================================

Enhanced duration efficiency analysis with comprehensive supplier benchmarking.

This module provides advanced efficiency metrics, supplier benchmarking,
and performance analytics for injection molding operations.

Features:
    - Multi-dimensional efficiency metrics with confidence intervals
    - Comprehensive supplier benchmarking framework
    - Tool consistency scoring across suppliers
    - Tier classification (Excellent/Good/Average/Needs Improvement/Poor)
    - Statistical analysis with confidence intervals
    - HTML report generation
    - CSV data exports

Benchmarking Methodology:
    - Normalized efficiency scoring
    - Tool consistency metrics
    - Performance ranking and tier classification
    - Cross-supplier comparisons

Usage:
    ```python
    from analysis.efficiency import run_analysis_api

    # Run analysis with simple API
    result = run_analysis_api(
        start_date="2025-01-01",
        end_date="2025-10-27",
        vendor_names=["Vantis industries SCS"],
        save_csv=True,
        save_html=True
    )

    print(f"Total suppliers: {result['supplier_summary']['total_suppliers']}")
    print(f"Mean efficiency: {result['efficiency_summary']['mean_efficiency']}%")
    ```

Author: Utku Gulbardak
Date: 2025-10-27
"""

# Main API
from .api import run_analysis_api

# Core functions
from .core import (
    benchmark_operators,
    benchmark_suppliers,
    calculate_duration_efficiency,
    create_snowpark_session,
    detect_shift_patterns,
    fetch_efficiency_data,
)

# Models
from .models import classify_supplier_tier, get_default_config, get_tier_color

# Reporting
from .reporting import generate_html_report

__version__ = "3.0.0"
__author__ = "Utku Gulbardak"

__all__ = [
    # Main API
    "run_analysis_api",
    # Models
    "get_default_config",
    "classify_supplier_tier",
    "get_tier_color",
    # Core - Supplier
    "create_snowpark_session",
    "fetch_efficiency_data",
    "calculate_duration_efficiency",
    "benchmark_suppliers",
    # Core - Operator
    "benchmark_operators",
    "detect_shift_patterns",
    # Reporting
    "generate_html_report",
]
