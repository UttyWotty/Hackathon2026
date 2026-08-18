"""
Duration Deviation Reporting Package.

Exports visualization and HTML report generation functions.
"""

from .html_generator import generate_html_report
from .visualizations import (
    create_deviation_distribution_chart,
    create_performance_comparison_chart,
    create_supplier_comparison_chart,
    create_time_series_chart,
)

__all__ = [
    "create_deviation_distribution_chart",
    "create_performance_comparison_chart",
    "create_time_series_chart",
    "create_supplier_comparison_chart",
    "generate_html_report",
]
