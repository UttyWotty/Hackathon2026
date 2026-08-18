"""MCP tool adapters for chart and dashboard creation.

Wraps chart_factory and manufacturing_dashboard orchestration in plain functions
matching the create_chart and create_manufacturing_dashboard MCP tool signatures.
Returns plain result dicts (no HTTPException) so the tool dispatcher can call them directly.
"""

import logging
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]

from services.visualization.chart_factory import (
    PLOTLY_AVAILABLE,
    ChartParams,
    create_chart_by_type,
    save_chart_if_needed,
    update_chart_layout,
    validate_columns,
)
from services.visualization.manufacturing_dashboard import (
    SUBPLOT_HORIZONTAL_SPACING,
    SUBPLOT_VERTICAL_SPACING,
    add_metric_traces,
    build_subplot_titles,
    configure_dashboard_layout,
    fetch_dashboard_data,
)

logger = logging.getLogger(__name__)

DEFAULT_CHART_HEIGHT: int = 600
DEFAULT_CHART_WIDTH: int = 1000
DEFAULT_DASHBOARD_METRICS: List[str] = [
    "efficiency",
    "downtime",
    "quality",
    "production",
]
PLOTLY_CDN_INCLUDE: str = "cdn"
PLOTLY_NOT_INSTALLED_ERROR: str = "Plotly not installed. Run: pip install plotly"
SINGLE_COLUMN_THRESHOLD: int = 1


def create_chart(
    chart_type: str,
    data: List[Dict[str, Any]],
    x_column: str,
    y_column: str,
    title: str,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Create an interactive chart from row data.

    Args:
        chart_type: One of line, bar, scatter, pie, area, heatmap.
        data: List of row dicts with column-value pairs.
        x_column: Column name for the X axis.
        y_column: Column name(s) for the Y axis (comma-separated for multiple).
        title: Chart title.
        output_path: Optional file path to save the chart HTML.

    Returns:
        dict: status, chart metadata, and either output_file or inline html.
    """
    if not PLOTLY_AVAILABLE:
        return {"status": "error", "error": PLOTLY_NOT_INSTALLED_ERROR}

    try:
        df = pd.DataFrame(data)
        y_columns = validate_columns(df, x_column, y_column)
        params = ChartParams(
            title=title,
            height=DEFAULT_CHART_HEIGHT,
            width=DEFAULT_CHART_WIDTH,
            chart_type=chart_type,
        )
        fig = create_chart_by_type(df, x_column, y_columns, params)
        if fig is None:
            return {"status": "error", "error": "Failed to create chart"}

        update_chart_layout(fig, chart_type)
        output_file = save_chart_if_needed(fig, output_path)
        return {
            "status": "success",
            "chart_type": chart_type,
            "title": title,
            "data_points": len(df),
            "columns": list(df.columns),
            "output_file": output_file,
            "html": (
                fig.to_html(include_plotlyjs=PLOTLY_CDN_INCLUDE)
                if not output_file
                else None
            ),
        }
    except Exception as e:
        logger.error("create_chart tool failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}


async def create_manufacturing_dashboard(
    machine_id: str,
    start_date: str,
    end_date: str,
    metrics: Optional[List[str]] = None,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """Create a pre-built multi-chart manufacturing dashboard for one equipment.

    Args:
        machine_id: Equipment code to analyze.
        start_date: Start date (YYYY-MM-DD).
        end_date: End date (YYYY-MM-DD).
        metrics: Subset of efficiency, downtime, quality, production. Defaults to all.
        output_path: Optional file path to save the dashboard HTML.

    Returns:
        dict: status, dashboard metadata, and either output_file or inline html.
    """
    if not PLOTLY_AVAILABLE:
        return {"status": "error", "error": PLOTLY_NOT_INSTALLED_ERROR}

    try:
        from plotly.subplots import make_subplots  # type: ignore[import-untyped]

        metrics_to_include = metrics or DEFAULT_DASHBOARD_METRICS
        dashboard_data, data_source = await fetch_dashboard_data(
            machine_id, start_date, end_date
        )
        if dashboard_data is None or dashboard_data.empty:
            return {
                "status": "error",
                "error": "No data available for dashboard",
                "machine_id": machine_id,
            }

        num_metrics = len(metrics_to_include)
        rows = (num_metrics + 1) // 2
        cols = 2 if num_metrics > SINGLE_COLUMN_THRESHOLD else 1

        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=build_subplot_titles(metrics_to_include),
            vertical_spacing=SUBPLOT_VERTICAL_SPACING,
            horizontal_spacing=SUBPLOT_HORIZONTAL_SPACING,
        )
        add_metric_traces(fig, dashboard_data, metrics_to_include, cols)
        configure_dashboard_layout(
            fig, machine_id, start_date, end_date, rows, cols, num_metrics
        )

        output_file = save_chart_if_needed(fig, output_path)
        return {
            "status": "success",
            "dashboard_type": "manufacturing",
            "machine_id": machine_id,
            "date_range": "%s to %s" % (start_date, end_date),
            "metrics_included": metrics_to_include,
            "data_points": len(dashboard_data),
            "output_file": output_file,
            "html": (
                fig.to_html(include_plotlyjs=PLOTLY_CDN_INCLUDE)
                if not output_file
                else None
            ),
            "data_source": data_source,
        }
    except Exception as e:
        logger.error("create_manufacturing_dashboard tool failed: %s", e, exc_info=True)
        return {"status": "error", "error": str(e)}
