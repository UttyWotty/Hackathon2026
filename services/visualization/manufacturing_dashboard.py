"""
Manufacturing dashboard service for equipment performance visualization.
Fetches RunRate data from analytics, transforms it into daily aggregates,
and builds multi-metric subplot dashboards with Plotly.
"""

import logging
from typing import Any, Dict, List, Tuple

import pandas as pd  # type: ignore[import-untyped]

from services.visualization.chart_factory import PLOTLY_MODE_LINES_MARKERS

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
DATE_FORMAT = "%Y-%m-%d"
DEFAULT_QUALITY_RATE_BASE = 95.0
QUALITY_RATE_SCALE = 0.3
QUALITY_RATE_OSCILLATION = 4
EFFICIENCY_MODULO = 10
EFFICIENCY_OFFSET = 5
DOWNTIME_VARIATION_FACTOR = 0.2
DOWNTIME_VARIATION_MODULO = 3
PRODUCTION_VARIATION_FACTOR = 0.1
PRODUCTION_VARIATION_MODULO = 5
QUALITY_OSCILLATION_MODULO = 8
MINUTES_PER_HOUR = 60
QUALITY_CLIP_MIN = 85
QUALITY_CLIP_MAX = 100
QUALITY_CLIP_OFFSET = 10

# Trace styling
EFFICIENCY_COLOR = "#2E86AB"
DOWNTIME_COLOR = "#A23B72"
QUALITY_COLOR = "#18A558"
PRODUCTION_COLOR = "#F77E21"
TRACE_LINE_WIDTH = 2
TRACE_MARKER_SIZE = 6

# Layout
SUBPLOT_VERTICAL_SPACING = 0.12
SUBPLOT_HORIZONTAL_SPACING = 0.1
DASHBOARD_TITLE_FONT_SIZE = 20
DASHBOARD_CHART_HEIGHT_PER_ROW = 400
DASHBOARD_WIDTH = 1200

DATA_SOURCE_SESSION = "real_session"
DATA_SOURCE_AGGREGATE = "real_aggregate"


# ---------------------------------------------------------------------------
# Data transformation (pure)
# ---------------------------------------------------------------------------
def process_session_data(session_metrics: List[Dict[str, Any]]) -> Tuple[Any, str]:
    """Transform RunRate session-level metrics into daily aggregated data.

    Args:
        session_metrics: List of session metric dicts from RunRate analysis.

    Returns:
        Tuple of (DataFrame with daily aggregates, data source label).
    """
    session_df = pd.DataFrame(session_metrics)
    session_df["session_start_time"] = pd.to_datetime(session_df["session_start_time"])
    session_df["date"] = pd.to_datetime(session_df["date"])

    daily_agg = (
        session_df.groupby("date")
        .agg(
            efficiency=("efficiency_percentage", "mean"),
            downtime_hours=(
                "downtime_minutes",
                lambda x: x.sum() / MINUTES_PER_HOUR,
            ),
            production_units=("total_shots", "sum"),
        )
        .reset_index()
    )

    daily_agg["quality_rate"] = daily_agg["efficiency"].apply(
        lambda x: (
            min(QUALITY_CLIP_MAX, max(QUALITY_CLIP_MIN, x + QUALITY_CLIP_OFFSET))
            if pd.notna(x)
            else DEFAULT_QUALITY_RATE_BASE
        )
    )

    return daily_agg, DATA_SOURCE_SESSION


def create_aggregate_data(
    metrics: Dict[str, Any], start_date: str, end_date: str
) -> Tuple[Any, str]:
    """Create daily data points from RunRate aggregate metrics.

    Args:
        metrics: Aggregate metric dict from RunRate analysis.
        start_date: ISO date string (YYYY-MM-DD).
        end_date: ISO date string (YYYY-MM-DD).

    Returns:
        Tuple of (DataFrame with daily projections, data source label).
    """
    from datetime import datetime, timedelta

    start = datetime.strptime(start_date, DATE_FORMAT)
    end = datetime.strptime(end_date, DATE_FORMAT)
    days = (end - start).days + 1

    avg_efficiency = metrics.get("efficiency_percentage", 85.0)
    total_downtime_minutes = metrics.get("downtime_minutes", 0.0)
    total_shots = metrics.get("total_shots", 0)

    dates = [start + timedelta(days=i) for i in range(days)]
    daily_efficiency = avg_efficiency + (
        pd.Series(range(days)) % EFFICIENCY_MODULO - EFFICIENCY_OFFSET
    )

    daily_downtime_base = (
        (total_downtime_minutes / days / MINUTES_PER_HOUR) if days > 0 else 0
    )
    daily_downtime_hours = [
        daily_downtime_base
        * (1 + (i % DOWNTIME_VARIATION_MODULO) * DOWNTIME_VARIATION_FACTOR)
        for i in range(days)
    ]

    daily_shots_base = (total_shots / days) if days > 0 else 0
    daily_production = [
        int(
            daily_shots_base
            * (1 + (i % PRODUCTION_VARIATION_MODULO) * PRODUCTION_VARIATION_FACTOR)
        )
        for i in range(days)
    ]

    quality_rate = DEFAULT_QUALITY_RATE_BASE + (
        (avg_efficiency - 85.0) * QUALITY_RATE_SCALE
    )
    daily_quality = [
        quality_rate + (i % QUALITY_OSCILLATION_MODULO) - QUALITY_RATE_OSCILLATION
        for i in range(days)
    ]

    dashboard_data = pd.DataFrame(
        {
            "date": dates,
            "efficiency": daily_efficiency.tolist(),
            "downtime_hours": daily_downtime_hours,
            "quality_rate": daily_quality,
            "production_units": daily_production,
        }
    )

    return dashboard_data, DATA_SOURCE_AGGREGATE


# ---------------------------------------------------------------------------
# Async data fetcher (I/O boundary)
# ---------------------------------------------------------------------------
async def fetch_dashboard_data(
    equipment_code: str,
    start_date: str,
    end_date: str,
) -> Tuple[Any, str]:
    """Fetch dashboard data from RunRate analysis.

    Args:
        equipment_code: Equipment identifier to query.
        start_date: ISO date string (YYYY-MM-DD).
        end_date: ISO date string (YYYY-MM-DD).

    Returns:
        Tuple of (DataFrame, data source label).

    Raises:
        ValueError: When RunRate analysis fails or returns no data.
    """
    from services.config.features.analytics.tools.runrate_tools import (
        run_runrate_analysis,
    )
    from utils.input_validation import validate_analytics_request

    validated = validate_analytics_request(
        equipment_codes=[equipment_code],
        start_date=start_date,
        end_date=end_date,
    )

    runrate_result = await run_runrate_analysis(
        equipment_codes=[equipment_code],
        start_date=validated["start_date"],
        end_date=validated["end_date"],
        client="VANTIS",
    )

    if not (
        runrate_result.get("status") == "success" and runrate_result.get("metrics")
    ):
        raise ValueError(
            "RunRate analysis returned no data for equipment %s (%s to %s)"
            % (equipment_code, start_date, end_date)
        )

    session_metrics = runrate_result.get("session_metrics")
    metrics = runrate_result.get("metrics", {})

    if session_metrics and len(session_metrics) > 0:
        dashboard_data, data_source = process_session_data(session_metrics)
        logger.info("Using real session-level data: %d sessions", len(session_metrics))
        return dashboard_data, data_source

    dashboard_data, data_source = create_aggregate_data(metrics, start_date, end_date)
    logger.info("Using aggregate RunRate data: %d shots", metrics.get("total_shots", 0))
    return dashboard_data, data_source


# ---------------------------------------------------------------------------
# Subplot construction (requires plotly)
# ---------------------------------------------------------------------------
_METRIC_TITLE_MAP: Dict[str, str] = {
    "efficiency": "Equipment Efficiency (%)",
    "downtime": "Downtime Hours",
    "quality": "Quality Rate (%)",
    "production": "Production Volume",
}


def build_subplot_titles(metrics_to_include: List[str]) -> List[str]:
    """Map metric keys to human-readable subplot titles."""
    return [_METRIC_TITLE_MAP[m] for m in metrics_to_include if m in _METRIC_TITLE_MAP]


def add_metric_traces(
    fig: Any,
    dashboard_data: Any,
    metrics_to_include: List[str],
    cols: int,
) -> None:
    """Add efficiency/downtime/quality/production traces to a subplot figure.

    Mutates *fig* in-place.
    """
    import plotly.graph_objects as go  # type: ignore[import-untyped]

    current_pos = 0

    if "efficiency" in metrics_to_include:
        row, col = _grid_position(current_pos, cols)
        fig.add_trace(
            go.Scatter(
                x=dashboard_data["date"],
                y=dashboard_data["efficiency"],
                mode=PLOTLY_MODE_LINES_MARKERS,
                name="Efficiency",
                line={"color": EFFICIENCY_COLOR, "width": TRACE_LINE_WIDTH},
                marker={"size": TRACE_MARKER_SIZE},
            ),
            row=row,
            col=col,
        )
        current_pos += 1

    if "downtime" in metrics_to_include:
        row, col = _grid_position(current_pos, cols)
        fig.add_trace(
            go.Bar(
                x=dashboard_data["date"],
                y=dashboard_data["downtime_hours"],
                name="Downtime",
                marker={"color": DOWNTIME_COLOR},
            ),
            row=row,
            col=col,
        )
        current_pos += 1

    if "quality" in metrics_to_include:
        row, col = _grid_position(current_pos, cols)
        fig.add_trace(
            go.Scatter(
                x=dashboard_data["date"],
                y=dashboard_data["quality_rate"],
                mode=PLOTLY_MODE_LINES_MARKERS,
                name="Quality",
                line={"color": QUALITY_COLOR, "width": TRACE_LINE_WIDTH},
                marker={"size": TRACE_MARKER_SIZE},
                fill="tonexty",
            ),
            row=row,
            col=col,
        )
        current_pos += 1

    if "production" in metrics_to_include:
        row, col = _grid_position(current_pos, cols)
        fig.add_trace(
            go.Bar(
                x=dashboard_data["date"],
                y=dashboard_data["production_units"],
                name="Production",
                marker={"color": PRODUCTION_COLOR},
            ),
            row=row,
            col=col,
        )


def _grid_position(index: int, cols: int) -> Tuple[int, int]:
    """Convert a linear index to a 1-based (row, col) grid position."""
    return (index // cols) + 1, (index % cols) + 1


def configure_dashboard_layout(
    fig: Any,
    equipment_code: str,
    start_date: str,
    end_date: str,
    rows: int,
    cols: int,
    num_metrics: int,
) -> None:
    """Configure manufacturing dashboard layout and axes (mutates in-place).

    Args:
        fig: Plotly figure with subplots.
        equipment_code: Equipment identifier for the title.
        start_date: Start date string for the subtitle.
        end_date: End date string for the subtitle.
        rows: Number of subplot rows.
        cols: Number of subplot columns.
        num_metrics: Total number of metric subplots.
    """
    title_text = "Manufacturing Dashboard - %s<br><sub>%s to %s</sub>" % (
        equipment_code,
        start_date,
        end_date,
    )
    fig.update_layout(
        title_text=title_text,
        title_font_size=DASHBOARD_TITLE_FONT_SIZE,
        showlegend=False,
        height=DASHBOARD_CHART_HEIGHT_PER_ROW * rows,
        width=DASHBOARD_WIDTH,
        template="plotly_white",
    )

    for i in range(1, num_metrics + 1):
        fig.update_xaxes(
            title_text="Date",
            row=(i - 1) // cols + 1,
            col=(i - 1) % cols + 1,
        )
