"""
Chart factory for creating Plotly charts from DataFrames.
Provides validation, chart creation by type, layout styling, and file export.
All functions are pure chart-building logic with no HTTP/FastAPI dependencies.
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Plotly conditional import
# ---------------------------------------------------------------------------
try:
    import plotly.express as px  # type: ignore[import-untyped]
    import plotly.graph_objects as go  # type: ignore[import-untyped]

    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False
    logger.warning("Plotly not installed. Visualization features disabled.")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
PLOTLY_MODE_LINES_MARKERS = "lines+markers"
PLOTLY_MODE_LINES = "lines"
PLOTLY_MODE_MARKERS = "markers"
PLOTLY_TEMPLATE_WHITE = "plotly_white"
HOVERMODE_X_UNIFIED = "x unified"
HOVERMODE_CLOSEST = "closest"
LINE_HOVER_CHART_TYPES = {"line", "area"}
HEATMAP_MIN_COLUMNS = 3
PIVOT_AGG_FUNC = "mean"


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------
class ColumnNotFoundError(Exception):
    """Raised when a requested column does not exist in the DataFrame."""

    def __init__(self, column: str, available: List[str]) -> None:
        self.column = column
        self.available = available
        super().__init__(
            "Column '%s' not found in data. Available columns: %s" % (column, available)
        )


class UnsupportedChartTypeError(Exception):
    """Raised when the requested chart type is not supported."""

    def __init__(self, chart_type: str) -> None:
        self.chart_type = chart_type
        super().__init__(
            "Unsupported chart type: %s. Use: line, bar, scatter, pie, area, heatmap"
            % chart_type
        )


class InsufficientColumnsError(Exception):
    """Raised when the DataFrame lacks required columns for a chart type."""

    def __init__(self, required: int, actual: int) -> None:
        self.required = required
        self.actual = actual
        super().__init__(
            "Chart requires at least %d columns, but got %d" % (required, actual)
        )


# ---------------------------------------------------------------------------
# Public interface -- typed dict for chart params
# ---------------------------------------------------------------------------
class ChartParams:
    """Value object carrying common chart parameters."""

    def __init__(
        self,
        title: str,
        height: int,
        width: int,
        chart_type: str = "line",
        orientation: str = "v",
        line_shape: str = "linear",
        color_column: Optional[str] = None,
    ) -> None:
        self.title = title
        self.height = height
        self.width = width
        self.chart_type = chart_type
        self.orientation = orientation
        self.line_shape = line_shape
        self.color_column = color_column


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def validate_columns(df: Any, x_column: str, y_column: str) -> List[str]:
    """Validate that x and y columns exist in the DataFrame.

    Args:
        df: pandas DataFrame to check.
        x_column: Name of the x-axis column.
        y_column: Comma-separated y-axis column name(s).

    Returns:
        List of validated y-column names.

    Raises:
        ColumnNotFoundError: When a column is missing.
    """
    if x_column not in df.columns:
        raise ColumnNotFoundError(x_column, list(df.columns))

    y_columns = [col.strip() for col in y_column.split(",")]
    for col in y_columns:
        if col not in df.columns:
            raise ColumnNotFoundError(col, list(df.columns))
    return y_columns


# ---------------------------------------------------------------------------
# Individual chart creators
# ---------------------------------------------------------------------------
def create_line_chart(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Create a line chart (single or multi-series)."""
    if len(y_columns) == 1:
        fig = px.line(
            df,
            x=x_column,
            y=y_columns[0],
            title=params.title,
            height=params.height,
            width=params.width,
        )
        fig.update_traces(line_shape=params.line_shape)
        return fig

    fig = go.Figure()
    for y_col in y_columns:
        fig.add_trace(
            go.Scatter(
                x=df[x_column],
                y=df[y_col],
                mode=PLOTLY_MODE_LINES_MARKERS,
                name=y_col,
                line_shape=params.line_shape,
            )
        )
    fig.update_layout(
        title=params.title,
        xaxis_title=x_column,
        yaxis_title=", ".join(y_columns),
        height=params.height,
        width=params.width,
    )
    return fig


def create_bar_chart(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Create a bar chart with configurable orientation."""
    return px.bar(
        df,
        x=x_column,
        y=y_columns[0],
        title=params.title,
        orientation=params.orientation,
        height=params.height,
        width=params.width,
    )


def create_scatter_chart(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Create a scatter or bubble plot."""
    return px.scatter(
        df,
        x=x_column,
        y=y_columns[0],
        color=params.color_column if params.color_column else None,
        title=params.title,
        height=params.height,
        width=params.width,
    )


def create_pie_chart(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Create a pie chart."""
    return px.pie(
        df,
        names=x_column,
        values=y_columns[0],
        title=params.title,
        height=params.height,
        width=params.width,
    )


def create_area_chart(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Create an area chart (single or stacked)."""
    if len(y_columns) == 1:
        return px.area(
            df,
            x=x_column,
            y=y_columns[0],
            title=params.title,
            height=params.height,
            width=params.width,
        )

    fig = go.Figure()
    for y_col in y_columns:
        fill = "tozeroy" if y_col == y_columns[0] else "tonexty"
        fig.add_trace(
            go.Scatter(
                x=df[x_column],
                y=df[y_col],
                mode=PLOTLY_MODE_LINES,
                name=y_col,
                fill=fill,
                stackgroup="one",
            )
        )
    fig.update_layout(
        title=params.title,
        xaxis_title=x_column,
        yaxis_title=", ".join(y_columns),
        height=params.height,
        width=params.width,
    )
    return fig


def create_heatmap_chart(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Create a pivot-based heatmap chart.

    Raises:
        InsufficientColumnsError: When DataFrame has fewer than 3 columns.
    """
    if len(df.columns) < HEATMAP_MIN_COLUMNS:
        raise InsufficientColumnsError(HEATMAP_MIN_COLUMNS, len(df.columns))

    pivot_col = y_columns[0] if len(y_columns) == 1 else df.columns[2]
    pivot_df = df.pivot_table(
        index=x_column,
        columns=pivot_col,
        values=df.columns[-1],
        aggfunc=PIVOT_AGG_FUNC,
    )
    return px.imshow(
        pivot_df,
        title=params.title,
        labels={"x": y_columns[0], "y": x_column, "color": "Value"},
        height=params.height,
        width=params.width,
    )


# ---------------------------------------------------------------------------
# Dispatcher
# ---------------------------------------------------------------------------
_CHART_CREATORS: Dict[str, Any] = {
    "line": create_line_chart,
    "bar": create_bar_chart,
    "scatter": create_scatter_chart,
    "pie": create_pie_chart,
    "area": create_area_chart,
    "heatmap": create_heatmap_chart,
}


def create_chart_by_type(
    df: Any, x_column: str, y_columns: List[str], params: ChartParams
) -> Any:
    """Route to the correct chart creator based on chart_type.

    Raises:
        UnsupportedChartTypeError: When chart_type is not recognised.
    """
    creator = _CHART_CREATORS.get(params.chart_type)
    if not creator:
        raise UnsupportedChartTypeError(params.chart_type)
    return creator(df, x_column, y_columns, params)


# ---------------------------------------------------------------------------
# Dashboard trace builder (generic dashboards)
# ---------------------------------------------------------------------------
def build_dashboard_trace(
    df: Any, chart_type: str, x_col: str, y_cols: List[str], name: str
) -> Any:
    """Build a single Plotly trace for a generic dashboard subplot.

    Args:
        df: DataFrame with chart data.
        chart_type: One of line, bar, scatter, area.
        x_col: X-axis column name.
        y_cols: Y-axis column names (first is used for single-series types).
        name: Display name for the trace.

    Returns:
        A Plotly trace object (go.Scatter or go.Bar).
    """
    y_col = y_cols[0]

    if chart_type == "bar":
        return go.Bar(x=df[x_col], y=df[y_col], name=name)

    if chart_type == "scatter":
        return go.Scatter(x=df[x_col], y=df[y_col], mode=PLOTLY_MODE_MARKERS, name=name)

    if chart_type == "area":
        return go.Scatter(
            x=df[x_col],
            y=df[y_col],
            mode=PLOTLY_MODE_LINES,
            name=name,
            fill="tozeroy",
        )

    # Default to line chart (covers "line" and any unrecognized type)
    return go.Scatter(
        x=df[x_col], y=df[y_col], mode=PLOTLY_MODE_LINES_MARKERS, name=name
    )


# ---------------------------------------------------------------------------
# Layout and file I/O
# ---------------------------------------------------------------------------
def update_chart_layout(fig: Any, chart_type: str) -> None:
    """Apply common Plotly styling to a figure (mutates in-place)."""
    hovermode = (
        HOVERMODE_X_UNIFIED
        if chart_type in LINE_HOVER_CHART_TYPES
        else HOVERMODE_CLOSEST
    )
    fig.update_layout(template=PLOTLY_TEMPLATE_WHITE, hovermode=hovermode)


IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg"}


def save_chart_if_needed(
    fig: Any, output_path: Optional[str], *, detect_format: bool = False
) -> Optional[str]:
    """Save chart to file if output_path is provided.

    Args:
        fig: Plotly figure to export.
        output_path: Destination path, or None to skip.
        detect_format: When True, uses file extension to choose HTML vs image.
            When False (default), always writes HTML.

    Returns:
        The resolved file path string, or None if skipped.
    """
    if not output_path:
        return None

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if detect_format and path.suffix in IMAGE_EXTENSIONS:
        fig.write_image(str(path))
    elif detect_format and path.suffix != ".html":
        html_path = str(path) + ".html"
        fig.write_html(html_path)
        logger.info("Chart saved to: %s", html_path)
        return html_path
    else:
        fig.write_html(str(path))

    logger.info("Chart saved to: %s", path)
    return str(path)
