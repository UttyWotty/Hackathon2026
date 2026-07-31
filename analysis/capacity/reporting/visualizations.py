"""
Visualization functions for Capacity Analysis using Plotly.

This module provides interactive chart generation for capacity/OEE analysis:
- Daily production output with stacked losses
- OEE component breakdowns (Availability, Performance, Quality)
- Multi-OEE target comparisons
- Optimal output comparisons

Author: Utku Gulbardak
Date: 2025-10-27
"""

from typing import Dict

import pandas as pd  # type: ignore[import-untyped]
import plotly.graph_objects as go  # type: ignore[import-untyped]

# Constants
NO_DATA_TITLE = "No data to display"
ACTUAL_OUTPUT_LABEL = "Actual Output"
ACTUAL_OUTPUT_HOVER_TEMPLATE = "%{x}<br>Actual Output: %{y:.0f}<extra></extra>"
PLOTLY_MODE_LINES_MARKERS = "lines+markers"


def make_daily_visual(daily: pd.DataFrame, equipment_code: str) -> go.Figure:
    """
    Create stacked bar daily visualization with Optimal line and Gap annotations.

    Shows actual output plus performance and availability losses stacked to reach
    optimal output. Can show negative performance (overperformance) as gains.

    Args:
        daily: DataFrame with daily aggregated metrics including:
            - DAY: Date column
            - ACTUAL_OUTPUT: Actual parts produced
            - PERFORMANCE_LOSS: Performance loss (positive) or gain (negative)
            - AVAILABILITY_LOSS: Downtime-based loss
            - OPTIMAL_OUTPUT: Target output at 100% OEE
            - GAP: Difference between optimal and actual
        equipment_code: Equipment identifier for chart title

    Returns:
        go.Figure: Plotly figure with stacked bar chart

    Example:
        >>> fig = make_daily_visual(daily_df, "MX-7102")
        >>> fig.show()
    """
    if daily.empty:
        fig = go.Figure()
        fig.update_layout(title=NO_DATA_TITLE)
        return fig

    x = daily["DAY"].dt.strftime("%Y-%m-%d").tolist()
    optimal = daily["OPTIMAL_OUTPUT"].tolist()

    fig = go.Figure()

    # Actual Output - always positive
    fig.add_trace(
        go.Bar(
            name=ACTUAL_OUTPUT_LABEL,
            x=x,
            y=daily["ACTUAL_OUTPUT"],
            marker_color="#2E8B57",
            hovertemplate=ACTUAL_OUTPUT_HOVER_TEMPLATE,
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#ffffff", "size": 12},
        )
    )

    # Performance Loss - can be positive (loss) or negative (gain)
    # Split into positive and negative for better visualization
    performance_pos = [max(0, val) for val in daily["PERFORMANCE_LOSS"]]
    performance_neg = [min(0, val) for val in daily["PERFORMANCE_LOSS"]]

    # Positive Performance Loss (traditional loss)
    fig.add_trace(
        go.Bar(
            name="Performance Loss",
            x=x,
            y=performance_pos,
            marker_color="#FF8C00",
            hovertemplate="%{x}<br>Performance Loss: %{y:.0f}<extra></extra>",
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#ffffff", "size": 12},
        )
    )

    # Negative Performance Loss (overperformance gain)
    fig.add_trace(
        go.Bar(
            name="Performance Gain",
            x=x,
            y=performance_neg,
            marker_color="#32CD32",  # Lime green for gains
            hovertemplate="%{x}<br>Performance Gain: %{y:.0f}<extra></extra>",
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#ffffff", "size": 12},
        )
    )

    # Availability Loss - should always be positive
    fig.add_trace(
        go.Bar(
            name="Availability Loss",
            x=x,
            y=daily["AVAILABILITY_LOSS"],
            marker_color="#DC143C",
            hovertemplate="%{x}<br>Availability Loss: %{y:.0f}<extra></extra>",
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#ffffff", "size": 12},
        )
    )

    fig.update_layout(
        title={
            "text": f"{equipment_code} Actual vs Optimal Output (Daily)",
            "x": 0.02,
            "xanchor": "left",
        },
        barmode="stack",
        xaxis_title="Day",
        yaxis_title="Parts",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        template="plotly_white",
        height=520,
        margin={"l": 60, "r": 20, "t": 70, "b": 60},
    )

    # Add gap annotations above optimal output
    for xi, gap, p in zip(x, daily["GAP"], optimal):
        fig.add_annotation(
            x=xi,
            y=p,
            text=f"Gap {gap:.0f}",
            showarrow=False,
            yshift=10,
            font={"size": 12},
        )
    return fig


def make_oee_visual(daily: pd.DataFrame, equipment_code: str) -> go.Figure:
    """
    Create OEE visualization with Availability, Performance, Quality, and Calculated OEE.

    Line chart showing OEE components over time with target OEE reference line.

    Args:
        daily: DataFrame with daily metrics including:
            - DAY: Date column
            - AVAILABILITY: Availability ratio (0-1)
            - PERFORMANCE: Performance ratio (0-1)
            - QUALITY: Quality ratio (0-1)
            - OEE_SCORE: Calculated OEE (A×P×Q, 0-1)
            - TARGET_OEE: Target OEE ratio
        equipment_code: Equipment identifier for chart title

    Returns:
        go.Figure: Plotly figure with line chart

    Example:
        >>> fig = make_oee_visual(daily_df, "MX-7102")
        >>> fig.show()
    """
    if daily.empty:
        fig = go.Figure()
        fig.update_layout(title=NO_DATA_TITLE)
        return fig

    x = daily["DAY"].dt.strftime("%Y-%m-%d").tolist()

    fig = go.Figure()

    # OEE Components
    fig.add_trace(
        go.Scatter(
            name="Availability",
            x=x,
            y=daily["AVAILABILITY"] * 100,  # Convert to percentage
            mode=PLOTLY_MODE_LINES_MARKERS,
            line={"color": "#1f77b4", "width": 3},
            marker={"size": 8},
            hovertemplate="%{x}<br>Availability: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Performance",
            x=x,
            y=daily["PERFORMANCE"] * 100,  # Convert to percentage
            mode=PLOTLY_MODE_LINES_MARKERS,
            line={"color": "#ff7f0e", "width": 3},
            marker={"size": 8},
            hovertemplate="%{x}<br>Performance: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Quality",
            x=x,
            y=daily["QUALITY"] * 100,  # Convert to percentage
            mode=PLOTLY_MODE_LINES_MARKERS,
            line={"color": "#2ca02c", "width": 3},
            marker={"size": 8},
            hovertemplate="%{x}<br>Quality: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_trace(
        go.Scatter(
            name="OEE Score",
            x=x,
            y=daily["OEE_SCORE"] * 100,  # Convert to percentage
            mode=PLOTLY_MODE_LINES_MARKERS,
            line={"color": "#d62728", "width": 4},
            marker={"size": 10},
            hovertemplate="%{x}<br>OEE Score: %{y:.1f}%<extra></extra>",
        )
    )

    # Target OEE line
    target_oee = daily["TARGET_OEE"].iloc[0] * 100  # Convert to percentage
    fig.add_hline(
        y=target_oee,
        line_dash="dash",
        line_color="#9467bd",
        annotation_text=f"Target OEE: {target_oee:.0f}%",
        annotation_position="top right",
    )

    fig.update_layout(
        title={
            "text": f"{equipment_code} OEE Components (Daily)",
            "x": 0.02,
            "xanchor": "left",
        },
        xaxis_title="Day",
        yaxis_title="Percentage (%)",
        yaxis={"range": [0, 105]},  # Show 0-105% range
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        template="plotly_white",
        height=520,
        margin={"l": 60, "r": 20, "t": 70, "b": 60},
    )
    return fig


def make_combined_oee_visual(
    all_daily_data: Dict[float, pd.DataFrame], equipment_code: str
) -> go.Figure:
    """
    Create combined visualization showing Optimal Output across all OEE targets.

    Grouped bar chart comparing actual output against optimal output at different
    OEE target levels (50%, 60%, 70%, 80%, 90%, 100%).

    Args:
        all_daily_data: Dict mapping OEE target (e.g., 0.60) to daily DataFrame
        equipment_code: Equipment identifier for chart title

    Returns:
        go.Figure: Plotly figure with grouped bar chart

    Example:
        >>> all_data = {0.50: df_50, 0.60: df_60, ..., 1.00: df_100}
        >>> fig = make_combined_oee_visual(all_data, "MX-7102")
        >>> fig.show()
    """
    if not all_daily_data:
        fig = go.Figure()
        fig.update_layout(title=NO_DATA_TITLE)
        return fig

    # Use the first dataset to get dates
    first_data = list(all_daily_data.values())[0]
    x = first_data["DAY"].dt.strftime("%Y-%m-%d").tolist()

    fig = go.Figure()

    # Color scheme for different OEE targets
    colors = {
        0.50: "#d32f2f",  # Red
        0.60: "#f57c00",  # Orange
        0.70: "#fbc02d",  # Yellow
        0.80: "#7b1fa2",  # Purple
        0.90: "#388e3c",  # Green
        1.00: "#1976d2",  # Blue
    }

    # Add Actual Output (same for all OEE targets)
    fig.add_trace(
        go.Bar(
            name=ACTUAL_OUTPUT_LABEL,
            x=x,
            y=first_data["ACTUAL_OUTPUT"],
            marker_color="#2E8B57",
            hovertemplate=ACTUAL_OUTPUT_HOVER_TEMPLATE,
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#ffffff", "size": 10},
        )
    )

    # Add Optimal Output for each OEE target
    for oee_target in sorted(all_daily_data.keys()):
        daily = all_daily_data[oee_target]
        fig.add_trace(
            go.Bar(
                name=f"{int(oee_target * 100)}% OEE",
                x=x,
                y=daily["OPTIMAL_OUTPUT"],
                marker_color=colors[oee_target],
                hovertemplate=f"%{{x}}<br>{int(oee_target * 100)}% OEE: %{{y:.0f}}<extra></extra>",
                texttemplate="%{y:.0f}",
                textposition="inside",
                textfont={"color": "#ffffff", "size": 10},
            )
        )

    fig.update_layout(
        title={
            "text": f"{equipment_code} Multi-OEE Optimal Output Comparison (Daily)",
            "x": 0.02,
            "xanchor": "left",
        },
        barmode="group",
        xaxis_title="Day",
        yaxis_title="Parts",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        template="plotly_white",
        height=520,
        margin={"l": 60, "r": 20, "t": 70, "b": 60},
    )
    return fig


def make_optimal_output_visual(daily: pd.DataFrame, equipment_code: str) -> go.Figure:
    """
    Create optimal output comparison visualization.

    Simple grouped bar chart comparing actual output to optimal output at 100% OEE.

    Args:
        daily: DataFrame with daily metrics including:
            - DAY: Date column
            - ACTUAL_OUTPUT: Actual parts produced
            - OPTIMAL_OUTPUT: Target output at 100% OEE
        equipment_code: Equipment identifier for chart title

    Returns:
        go.Figure: Plotly figure with grouped bar chart

    Example:
        >>> fig = make_optimal_output_visual(daily_df, "MX-7102")
        >>> fig.show()
    """
    if daily.empty:
        fig = go.Figure()
        fig.update_layout(title=NO_DATA_TITLE)
        return fig

    x = daily["DAY"].dt.strftime("%Y-%m-%d").tolist()

    fig = go.Figure()

    # Optimal output at different levels
    fig.add_trace(
        go.Bar(
            name=ACTUAL_OUTPUT_LABEL,
            x=x,
            y=daily["ACTUAL_OUTPUT"],
            marker_color="#2E8B57",
            hovertemplate=ACTUAL_OUTPUT_HOVER_TEMPLATE,
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#ffffff", "size": 10},
        )
    )
    fig.add_trace(
        go.Bar(
            name="Optimal Output (100% OEE)",
            x=x,
            y=daily["OPTIMAL_OUTPUT"],
            marker_color="#FFD700",
            hovertemplate="%{x}<br>Optimal Output (100% OEE): %{y:.0f}<extra></extra>",
            texttemplate="%{y:.0f}",
            textposition="inside",
            textfont={"color": "#000000", "size": 10},
        )
    )

    fig.update_layout(
        title={
            "text": f"{equipment_code} Optimal Output Comparison (Daily)",
            "x": 0.02,
            "xanchor": "left",
        },
        barmode="group",
        xaxis_title="Day",
        yaxis_title="Parts",
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        template="plotly_white",
        height=520,
        margin={"l": 60, "r": 20, "t": 70, "b": 60},
    )
    return fig
