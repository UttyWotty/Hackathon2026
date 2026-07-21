"""
Visualization service package for chart creation and manufacturing dashboards.
Re-exports the public API from chart_factory and manufacturing_dashboard modules.
This package separates Plotly chart logic from the FastAPI router layer.
"""

from services.visualization.chart_factory import (
    PLOTLY_AVAILABLE,
    PLOTLY_MODE_LINES_MARKERS,
    build_dashboard_trace,
    create_chart_by_type,
    save_chart_if_needed,
    update_chart_layout,
    validate_columns,
)
from services.visualization.manufacturing_dashboard import (
    add_metric_traces,
    build_subplot_titles,
    configure_dashboard_layout,
    fetch_dashboard_data,
)

__all__ = [
    "PLOTLY_AVAILABLE",
    "PLOTLY_MODE_LINES_MARKERS",
    "build_dashboard_trace",
    "create_chart_by_type",
    "save_chart_if_needed",
    "update_chart_layout",
    "validate_columns",
    "add_metric_traces",
    "build_subplot_titles",
    "configure_dashboard_layout",
    "fetch_dashboard_data",
]
