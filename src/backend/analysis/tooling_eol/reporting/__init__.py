"""
Tooling EOL Reporting Package.

Exports reporting functionality for tooling end-of-life prediction.
"""

from .html_generator import generate_html_report, wrap_table_in_html

__all__ = [
    "wrap_table_in_html",
    "generate_html_report",
]
