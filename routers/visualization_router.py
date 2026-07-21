"""
Visualization Router - Thin HTTP layer for chart and dashboard endpoints.
Defines Pydantic request models and delegates all logic to the visualization service.
No chart-building or data-fetching logic lives here.
"""

import logging
from typing import Any, Callable, Dict, List, Optional

import pandas as pd  # type: ignore[import-untyped]
from fastapi import APIRouter, HTTPException  # type: ignore[import-untyped]
from pydantic import BaseModel, Field  # type: ignore[import-untyped]

from services.visualization.chart_factory import (
    PLOTLY_AVAILABLE,
    ChartParams,
    ColumnNotFoundError,
    InsufficientColumnsError,
    UnsupportedChartTypeError,
    build_dashboard_trace,
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
from utils.error_handling import sanitize_error_message
from utils.input_validation import InputValidationError

logger = logging.getLogger(__name__)

# Constants
CHART_TITLE_DESC = "Chart title"
OUTPUT_PATH_DESC = "Output file path"
PLOTLY_NOT_INSTALLED_ERROR = "Plotly not installed. Run: pip install plotly"
VIZ_FAILED_ERROR = "Visualization operation failed. Please try again."
DEFAULT_CHART_HEIGHT = 600
DEFAULT_CHART_WIDTH = 1000
DEFAULT_PIE_WIDTH = 800
DEFAULT_METRICS = ["efficiency", "downtime", "quality", "production"]
PLOTLY_CDN_INCLUDE = "cdn"
GRID_LAYOUT = "grid"
MIN_GRID_COLS_THRESHOLD = 1

router = APIRouter()


# Request Models
class UniversalChartRequest(BaseModel):
    """Universal chart request for all chart types."""

    chart_type: str = Field(
        ..., description="Chart type: line, bar, scatter, pie, area, heatmap"
    )
    data: List[Dict[str, Any]] = Field(
        ..., description="Data for chart (list of dictionaries)"
    )
    x_column: str = Field(..., description="Column name for X-axis")
    y_column: str = Field(
        ..., description="Column name for Y-axis (comma-separated for multiple)"
    )
    title: str = Field(..., description=CHART_TITLE_DESC)
    output_path: Optional[str] = Field(None, description="Output file path (HTML)")
    height: int = Field(DEFAULT_CHART_HEIGHT, description="Chart height in pixels")
    width: int = Field(DEFAULT_CHART_WIDTH, description="Chart width in pixels")
    orientation: str = Field("v", description="Bar orientation: 'v' or 'h'")
    line_shape: str = Field("linear", description="Line shape: linear, spline, hv, vh")
    color_column: Optional[str] = Field(None, description="Column for color coding")


class ChartDataRequest(BaseModel):
    """Base request model for single-type chart endpoints."""

    data: List[Dict[str, Any]] = Field(
        ..., description="Data for chart (list of dictionaries)"
    )
    x_column: str = Field(..., description="Column name for X-axis")
    y_column: str = Field(..., description="Column name for Y-axis")
    title: str = Field("Chart", description=CHART_TITLE_DESC)
    output_path: Optional[str] = Field(
        None, description="Output file path (HTML or PNG)"
    )
    height: int = Field(DEFAULT_CHART_HEIGHT, description="Chart height in pixels")
    width: int = Field(DEFAULT_CHART_WIDTH, description="Chart width in pixels")


class BarChartRequest(ChartDataRequest):
    """Bar chart request with orientation."""

    orientation: str = Field(
        "v", description="Bar orientation: 'v' (vertical) or 'h' (horizontal)"
    )


class LineChartRequest(ChartDataRequest):
    """Line chart request with line shape."""

    line_shape: str = Field(
        "linear", description="Line shape: 'linear', 'spline', 'hv', 'vh'"
    )


class ScatterPlotRequest(ChartDataRequest):
    """Scatter plot request with optional size and color columns."""

    size_column: Optional[str] = Field(
        None, description="Column for bubble size (optional)"
    )
    color_column: Optional[str] = Field(
        None, description="Column for color coding (optional)"
    )


class PieChartRequest(BaseModel):
    """Pie chart request with labels and values columns."""

    data: List[Dict[str, Any]] = Field(..., description="Data for pie chart")
    labels_column: str = Field(..., description="Column for labels")
    values_column: str = Field(..., description="Column for values")
    title: str = Field("Pie Chart", description=CHART_TITLE_DESC)
    output_path: Optional[str] = Field(None, description=OUTPUT_PATH_DESC)
    height: int = Field(DEFAULT_CHART_HEIGHT, description="Chart height")
    width: int = Field(DEFAULT_PIE_WIDTH, description="Chart width")


class DashboardRequest(BaseModel):
    """Multi-chart dashboard request."""

    charts: List[Dict[str, Any]] = Field(
        ..., description="List of chart configurations"
    )
    layout: str = Field("grid", description="Dashboard layout: 'grid' or 'vertical'")
    title: str = Field("Dashboard", description="Dashboard title")
    output_path: Optional[str] = Field(None, description=OUTPUT_PATH_DESC)


class ManufacturingDashboardRequest(BaseModel):
    """Manufacturing dashboard request for equipment reports."""

    equipment_code: str = Field(..., description="Equipment code to analyze")
    start_date: str = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: str = Field(..., description="End date (YYYY-MM-DD)")
    metrics: Optional[List[str]] = Field(
        None,
        description="Metrics to include: efficiency, downtime, quality, production",
    )
    output_path: Optional[str] = Field(None, description=OUTPUT_PATH_DESC)


# Helpers
def _require_plotly() -> None:
    """Raise 503 if Plotly is not installed."""
    if not PLOTLY_AVAILABLE:
        raise HTTPException(status_code=503, detail=PLOTLY_NOT_INSTALLED_ERROR)


def _handle_chart_domain_error(exc: Exception) -> None:
    """Convert domain exceptions from chart_factory into HTTPExceptions."""
    if isinstance(
        exc, (ColumnNotFoundError, UnsupportedChartTypeError, InsufficientColumnsError)
    ):
        raise HTTPException(status_code=400, detail=str(exc))


def _run_simple_chart(
    chart_type: str,
    data: List[Dict[str, Any]],
    output_path: Optional[str],
    title: str,
    fig_builder: Callable[[Any], Any],
    count_label: str = "data_points",
) -> Dict[str, Any]:
    """Shared flow for the four simple chart endpoints.

    Args:
        chart_type: Chart type key for the response.
        data: Raw data dicts from the request.
        output_path: Optional save path.
        title: Chart title.
        fig_builder: Callable(df) -> Plotly figure.
        count_label: Key name for the row-count field in the response.

    Returns:
        Success response dict.
    """
    df = pd.DataFrame(data)
    try:
        fig = fig_builder(df)
    except (ValueError, KeyError) as exc:
        # Plotly raises ValueError/KeyError when a requested axis is not a
        # column in the supplied data: that is bad client input, not a 500.
        raise HTTPException(
            status_code=400, detail="Invalid chart request: %s" % exc
        ) from exc
    output_file = save_chart_if_needed(fig, output_path, detect_format=True)
    return {
        "status": "success",
        "chart_type": chart_type,
        "title": title,
        count_label: len(df),
        "output_file": output_file,
        "html": fig.to_html() if not output_file else None,
    }


# Endpoints
@router.get("/", summary="Visualization Service Info")
async def visualization_info() -> Dict[str, Any]:
    """Get information about the visualization service."""
    return {
        "service": "Visualization Service",
        "description": "Create charts and graphs from data",
        "plotly_available": PLOTLY_AVAILABLE,
        "supported_charts": [
            "line",
            "bar",
            "scatter",
            "pie",
            "area",
            "heatmap",
            "box",
            "histogram",
            "dashboard",
        ],
        "llm_tools": ["create_chart", "create_manufacturing_dashboard"],
    }


@router.post("/create", summary="Create Chart (Universal)")
async def create_chart_universal(request: UniversalChartRequest) -> Dict[str, Any]:
    """Universal chart creator -- supports line, bar, scatter, pie, area, heatmap."""
    _require_plotly()
    try:
        df = pd.DataFrame(request.data)
        y_columns = validate_columns(df, request.x_column, request.y_column)
        params = ChartParams(
            title=request.title,
            height=request.height,
            width=request.width,
            chart_type=request.chart_type,
            orientation=request.orientation,
            line_shape=request.line_shape,
            color_column=request.color_column,
        )
        fig = create_chart_by_type(df, request.x_column, y_columns, params)
        if fig is None:
            raise HTTPException(status_code=500, detail="Failed to create chart")

        update_chart_layout(fig, request.chart_type)
        output_file = save_chart_if_needed(fig, request.output_path)
        html_string = fig.to_html(include_plotlyjs=PLOTLY_CDN_INCLUDE)

        return {
            "status": "success",
            "chart_type": request.chart_type,
            "title": request.title,
            "data_points": len(df),
            "columns": list(df.columns),
            "output_file": output_file,
            "html": html_string if not output_file else None,
            "message": "Chart created successfully with %d data points" % len(df),
        }
    except HTTPException:
        raise
    except Exception as e:
        _handle_chart_domain_error(e)
        logger.error("Chart creation error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(
            e, "Chart creation failed. Please check your input data and try again."
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/manufacturing-dashboard", summary="Create Manufacturing Dashboard")
async def create_manufacturing_dashboard(
    request: ManufacturingDashboardRequest,
) -> Dict[str, Any]:
    """Create a pre-built manufacturing dashboard for equipment analysis."""
    _require_plotly()
    try:
        from plotly.subplots import make_subplots  # type: ignore[import-untyped]

        metrics_to_include = request.metrics or DEFAULT_METRICS
        dashboard_data, data_source = await fetch_dashboard_data(
            request.equipment_code, request.start_date, request.end_date
        )
        if dashboard_data is None or dashboard_data.empty:
            raise HTTPException(
                status_code=404,
                detail="No data available for the requested equipment and date range",
            )

        num_metrics = len(metrics_to_include)
        rows = (num_metrics + 1) // 2
        cols = 2 if num_metrics > MIN_GRID_COLS_THRESHOLD else 1

        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=build_subplot_titles(metrics_to_include),
            vertical_spacing=SUBPLOT_VERTICAL_SPACING,
            horizontal_spacing=SUBPLOT_HORIZONTAL_SPACING,
        )
        add_metric_traces(fig, dashboard_data, metrics_to_include, cols)
        configure_dashboard_layout(
            fig,
            request.equipment_code,
            request.start_date,
            request.end_date,
            rows,
            cols,
            num_metrics,
        )

        output_file = save_chart_if_needed(fig, request.output_path)
        html_string = fig.to_html(include_plotlyjs=PLOTLY_CDN_INCLUDE)

        return {
            "status": "success",
            "dashboard_type": "manufacturing",
            "equipment_code": request.equipment_code,
            "date_range": "%s to %s" % (request.start_date, request.end_date),
            "metrics_included": metrics_to_include,
            "num_charts": len(metrics_to_include),
            "data_points": len(dashboard_data),
            "output_file": output_file,
            "html": html_string if not output_file else None,
            "message": "Manufacturing dashboard created with %d charts"
            % len(metrics_to_include),
            "data_source": data_source,
        }
    except HTTPException:
        raise
    except InputValidationError as e:
        raise HTTPException(status_code=400, detail="Invalid input: %s" % e) from e
    except Exception as e:
        logger.error("Dashboard creation error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(
            e,
            "Dashboard creation failed. Please check your input data and try again.",
        )
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/line-chart", summary="Create Line Chart")
async def create_line_chart(request: LineChartRequest) -> Dict[str, Any]:
    """Create a line chart from data."""
    _require_plotly()
    try:
        import plotly.express as local_px  # type: ignore[import-untyped]

        def _build(df: Any) -> Any:
            fig = local_px.line(
                df,
                x=request.x_column,
                y=request.y_column,
                title=request.title,
                height=request.height,
                width=request.width,
            )
            fig.update_traces(line_shape=request.line_shape)
            return fig

        return _run_simple_chart(
            "line",
            request.data,
            request.output_path,
            request.title,
            _build,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Line chart error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, VIZ_FAILED_ERROR)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/bar-chart", summary="Create Bar Chart")
async def create_bar_chart(request: BarChartRequest) -> Dict[str, Any]:
    """Create a bar chart from data."""
    _require_plotly()
    try:
        import plotly.express as local_px  # type: ignore[import-untyped]

        def _build(df: Any) -> Any:
            return local_px.bar(
                df,
                x=request.x_column,
                y=request.y_column,
                title=request.title,
                orientation=request.orientation,
                height=request.height,
                width=request.width,
            )

        return _run_simple_chart(
            "bar",
            request.data,
            request.output_path,
            request.title,
            _build,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Bar chart error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, VIZ_FAILED_ERROR)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/scatter-plot", summary="Create Scatter Plot")
async def create_scatter_plot(request: ScatterPlotRequest) -> Dict[str, Any]:
    """Create a scatter plot from data."""
    _require_plotly()
    try:
        import plotly.express as local_px  # type: ignore[import-untyped]

        def _build(df: Any) -> Any:
            return local_px.scatter(
                df,
                x=request.x_column,
                y=request.y_column,
                size=request.size_column,
                color=request.color_column,
                title=request.title,
                height=request.height,
                width=request.width,
            )

        return _run_simple_chart(
            "scatter",
            request.data,
            request.output_path,
            request.title,
            _build,
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Scatter plot error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, VIZ_FAILED_ERROR)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/pie-chart", summary="Create Pie Chart")
async def create_pie_chart(request: PieChartRequest) -> Dict[str, Any]:
    """Create a pie chart from data."""
    _require_plotly()
    try:
        import plotly.express as local_px  # type: ignore[import-untyped]

        def _build(df: Any) -> Any:
            return local_px.pie(
                df,
                names=request.labels_column,
                values=request.values_column,
                title=request.title,
                height=request.height,
                width=request.width,
            )

        return _run_simple_chart(
            "pie",
            request.data,
            request.output_path,
            request.title,
            _build,
            count_label="slices",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Pie chart error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, VIZ_FAILED_ERROR)
        raise HTTPException(status_code=500, detail=error_msg)


@router.post("/dashboard", summary="Create Dashboard")
async def create_dashboard(request: DashboardRequest) -> Dict[str, Any]:
    """Create a multi-chart dashboard."""
    _require_plotly()
    try:
        from plotly.subplots import make_subplots  # type: ignore[import-untyped]

        num_charts = len(request.charts)
        if num_charts == 0:
            raise HTTPException(status_code=400, detail="No charts provided")

        if request.layout == GRID_LAYOUT:
            cols = 2 if num_charts > MIN_GRID_COLS_THRESHOLD else 1
            rows = (num_charts + 1) // 2
        else:
            cols = 1
            rows = num_charts

        fig = make_subplots(
            rows=rows,
            cols=cols,
            subplot_titles=[
                c.get("title", "Chart %d" % (i + 1))
                for i, c in enumerate(request.charts)
            ],
        )

        for i, chart_config in enumerate(request.charts):
            row, col = (i // cols) + 1, (i % cols) + 1
            chart_data = chart_config.get("data", [])
            chart_type = chart_config.get("chart_type", "line")
            x_col = chart_config.get("x_column")
            y_col = chart_config.get("y_column")
            chart_name = chart_config.get("title", "Chart %d" % (i + 1))

            if not chart_data or not x_col or not y_col:
                raise HTTPException(
                    status_code=400,
                    detail="Chart %d missing required fields: data, x_column, y_column"
                    % (i + 1),
                )

            df = pd.DataFrame(chart_data)
            validate_columns(df, x_col, y_col)
            y_cols = [c.strip() for c in y_col.split(",")]
            trace = build_dashboard_trace(df, chart_type, x_col, y_cols, chart_name)
            fig.add_trace(trace, row=row, col=col)

        fig.update_layout(title_text=request.title, showlegend=True)
        output_file = save_chart_if_needed(fig, request.output_path)

        return {
            "status": "success",
            "chart_type": "dashboard",
            "title": request.title,
            "num_charts": num_charts,
            "layout": request.layout,
            "output_file": output_file,
            "html": fig.to_html() if not output_file else None,
        }
    except HTTPException:
        raise
    except Exception as e:
        _handle_chart_domain_error(e)
        logger.error("Dashboard error: %s", e, exc_info=True)
        error_msg = sanitize_error_message(e, VIZ_FAILED_ERROR)
        raise HTTPException(status_code=500, detail=error_msg)
