"""
CT Efficiency Reporting Package.

Exports HTML report generation and interactive chart functions.
"""

from .analysis_report import generate_analysis_report
from .charts import generate_all_charts
from .html_generator import generate_html_report

__all__ = [
    "generate_html_report",
    "generate_analysis_report",
    "generate_all_charts",
]
