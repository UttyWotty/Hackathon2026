"""
Cycle Time Deviation Analysis Module
=====================================

Comprehensive CT deviation metrics for injection molding operations.

This module analyzes cycle time (CT) deviations from approved specifications,
providing insights into process stability and efficiency.

Features:
    - Snowflake database integration for shot-level data
    - CT deviation categorization (Excellent to Critical)
    - Efficiency scoring based on target adherence
    - Process stability metrics
    - Shot-level analysis (above/below/on target)
    - Statistical analysis with confidence intervals
    - Visualization generation (deviation heatmaps, trends, distributions)
    - HTML and CSV report generation
    - Equipment and supplier comparisons

Deviation Categories:
    - Excellent: ≤5% deviation from approved CT
    - Good: 5-10% deviation
    - Acceptable: 10-15% deviation
    - Poor: 15-20% deviation
    - Critical: >20% deviation

Usage:
    ```python
    from analysis.ct_deviation import run_analysis_api

    # Run analysis with simple API
    result = run_analysis_api(
        start_date="2025-01-01",
        end_date="2025-10-27",
        equipment_codes=["EMA-4104", "EMA-4110"],
        save_csv=True,
        save_html=True
    )

    print(f"Average deviation: {result['summary']['avg_deviation']}%")
    print(f"Total equipment analyzed: {result['summary']['total_equipment']}")
    ```

Author: Utku Gulbardak
Date: 2025-10-27
"""

# Main API
from .api import run_analysis_api

# Core functions
from .core import (
    calculate_deviation_metrics,
    create_snowpark_session,
    fetch_ct_deviation_data,
    generate_summary_statistics,
)

# Models
from .models import (
    calculate_efficiency_score,
    calculate_stability_score,
    categorize_deviation,
)

# Reporting
from .reporting import (
    create_deviation_distribution_chart,
    create_performance_comparison_chart,
    generate_html_report,
)

__version__ = "2.0.0"
__author__ = "Utku Gulbardak"

__all__ = [
    # Main API
    "run_analysis_api",
    # Models
    "categorize_deviation",
    "calculate_efficiency_score",
    "calculate_stability_score",
    # Core
    "create_snowpark_session",
    "fetch_ct_deviation_data",
    "calculate_deviation_metrics",
    "generate_summary_statistics",
    # Reporting
    "create_deviation_distribution_chart",
    "create_performance_comparison_chart",
    "generate_html_report",
]
