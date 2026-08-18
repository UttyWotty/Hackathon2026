"""
Interactive Chart Generator for Duration Efficiency Analysis.

This module generates standalone interactive HTML charts using plotly for
operator shift analysis, tool comparison, and approved target staleness detection.
"""

import logging
import os
from typing import Dict, List

import plotly.graph_objects as go  # type: ignore[import-untyped]
from plotly.subplots import make_subplots  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Muted color palette for PDF-friendly output
COLORS = [
    "#4A7C94",  # steel blue
    "#7BA38C",  # sage green
    "#C4956A",  # warm tan
    "#8B7BAA",  # muted purple-gray
    "#D4827E",  # dusty rose
    "#6B9DAD",  # teal
    "#A8A064",  # olive
    "#B07D9E",  # mauve
]

LAYOUT_DEFAULTS = dict(
    font=dict(family="Inter, Segoe UI, sans-serif", size=12, color="#333"),
    plot_bgcolor="#FAFAFA",
    paper_bgcolor="#FFFFFF",
    margin=dict(l=60, r=40, t=60, b=60),
)


def _save_chart(fig: go.Figure, output_dir: str, filename: str) -> str:
    """Save a plotly figure as standalone HTML.

    Args:
        fig: Plotly figure
        output_dir: Output directory
        filename: Filename without extension

    Returns:
        Path to saved HTML file
    """
    path = os.path.join(output_dir, f"{filename}.html")
    fig.write_html(path, include_plotlyjs="cdn")
    logger.info("Chart saved to %s", path)
    return path


# ==================== Operator / Shift Charts ==================== #


def chart_shift_variance(
    shift_analyses: List,
    output_dir: str,
) -> str:
    """Bar chart: within-day std vs across-day std per equipment.

    Shows the variance decomposition proving operators don't matter.

    Args:
        shift_analyses: List of EquipmentShiftAnalysis objects
        output_dir: Output directory

    Returns:
        Path to saved chart
    """
    equipment = []
    within_vals = []
    across_vals = []
    ratios = []

    for a in shift_analyses:
        if a.variance is None:
            continue
        equipment.append(a.machine_id)
        within_vals.append(a.variance.within_day_std)
        across_vals.append(a.variance.across_day_std)
        ratios.append(a.variance.operator_ratio)

    if not equipment:
        return ""

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            name="Within-Day Std (Operator Effect)",
            x=equipment,
            y=within_vals,
            marker_color=COLORS[0],
        )
    )
    fig.add_trace(
        go.Bar(
            name="Across-Day Std (Machine/Tooling Effect)",
            x=equipment,
            y=across_vals,
            marker_color=COLORS[1],
        )
    )
    fig.add_trace(
        go.Scatter(
            name="Operator Ratio",
            x=equipment,
            y=ratios,
            yaxis="y2",
            mode="markers+lines",
            marker=dict(size=10, color=COLORS[2]),
            line=dict(dash="dot", color=COLORS[2]),
        )
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Operator vs Machine Variance Decomposition",
        barmode="group",
        yaxis=dict(title="Std Dev (pct points)"),
        yaxis2=dict(
            title="Operator Ratio", overlaying="y", side="right", range=[0, 1.5]
        ),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
        height=450,
    )

    # Add threshold line at 0.3
    fig.add_hline(
        y=0.3,
        line_dash="dash",
        line_color="#999",
        annotation_text="Operator impact threshold (0.3)",
        yref="y2",
    )

    return _save_chart(fig, output_dir, "chart_operator_variance")


# ==================== Tool Comparison Charts ==================== #


MAX_CHART_GROUPS = 10  # Limit subplots to avoid layout explosion


def chart_tool_comparison(
    tool_groups: List,
    output_dir: str,
) -> str:
    """Grouped bar chart: equipment efficiency within each approved duration group.

    Args:
        tool_groups: List of ApprovedCTGroup objects (top N by equipment count)
        output_dir: Output directory

    Returns:
        Path to saved chart
    """
    if not tool_groups:
        return ""

    # Limit to top groups by equipment count to keep chart readable
    display_groups = tool_groups[:MAX_CHART_GROUPS]
    group_count = len(display_groups)
    fig = make_subplots(
        rows=group_count,
        cols=1,
        subplot_titles=[
            f"Approved Duration: {g.target_duration}s - {', '.join(g.product_names[:2])}"
            for g in display_groups
        ],
        vertical_spacing=max(0.01, 0.12 / max(1, group_count / 4)),
    )

    for i, group in enumerate(display_groups, start=1):
        equip_codes = [t.machine_id for t in group.tools]
        efficiencies = [t.mean_efficiency_pct for t in group.tools]
        deviations = [t.deviation_from_group_mean for t in group.tools]

        bar_colors = [COLORS[0] if d >= 0 else COLORS[4] for d in deviations]

        fig.add_trace(
            go.Bar(
                x=equip_codes,
                y=efficiencies,
                marker_color=bar_colors,
                text=[f"{e:.1f}%" for e in efficiencies],
                textposition="outside",
                showlegend=False,
            ),
            row=i,
            col=1,
        )

        # Group mean line
        fig.add_hline(
            y=group.group_mean_efficiency,
            row=i,
            col=1,
            line_dash="dash",
            line_color="#999",
            annotation_text=f"Group Mean: {group.group_mean_efficiency:.1f}%",
        )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Tool Performance Within Same-Part Groups",
        height=300 * group_count,
        showlegend=False,
    )
    fig.update_yaxes(title_text="Efficiency %")

    return _save_chart(fig, output_dir, "chart_tool_comparison")


def chart_tool_monthly_trend(
    windowed_groups: List,
    output_dir: str,
) -> str:
    """Line chart: equipment efficiency over time within each group.

    Args:
        windowed_groups: List of WindowedGroupResult objects
        output_dir: Output directory

    Returns:
        Path to saved chart
    """
    if not windowed_groups:
        return ""

    display_groups = windowed_groups[:MAX_CHART_GROUPS]
    group_count = len(display_groups)
    fig = make_subplots(
        rows=group_count,
        cols=1,
        subplot_titles=[
            f"Approved Duration: {g.target_duration}s - Monthly Trends" for g in display_groups
        ],
        vertical_spacing=max(0.01, 0.12 / max(1, group_count / 4)),
    )

    for i, group in enumerate(display_groups, start=1):
        # Group window stats by equipment
        by_equip: Dict[str, List] = {}
        for s in group.window_stats:
            by_equip.setdefault(s.machine_id, []).append(s)

        for j, (equip_code, stats) in enumerate(sorted(by_equip.items())):
            stats_sorted = sorted(stats, key=lambda s: s.window)
            windows = [s.window for s in stats_sorted]
            effs = [s.mean_efficiency_pct for s in stats_sorted]

            fig.add_trace(
                go.Scatter(
                    x=windows,
                    y=effs,
                    mode="lines+markers",
                    name=equip_code,
                    line=dict(color=COLORS[j % len(COLORS)]),
                    marker=dict(size=5),
                    legendgroup=f"group{i}",
                    showlegend=(i == 1),
                ),
                row=i,
                col=1,
            )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Equipment Performance Over Time (Monthly Windows)",
        height=350 * group_count,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )
    fig.update_yaxes(title_text="Efficiency %")

    return _save_chart(fig, output_dir, "chart_monthly_trends")


# ==================== Staleness Charts ==================== #


def chart_staleness_overview(
    staleness_results: List,
    output_dir: str,
) -> str:
    """Horizontal bar chart: approved duration vs actual duration with severity coloring.

    Args:
        staleness_results: List of StalenessResult objects
        output_dir: Output directory

    Returns:
        Path to saved chart
    """
    if not staleness_results:
        return ""

    labels = [
        f"{r.target_duration}s - {', '.join(r.product_names[:2])}" for r in staleness_results
    ]

    severity_colors = {
        "ok": "#7BA38C",
        "warning": "#C4956A",
        "stale": "#D4827E",
        "severely_stale": "#B05050",
    }

    fig = go.Figure()

    # Approved Duration bars
    fig.add_trace(
        go.Bar(
            y=labels,
            x=[r.target_duration for r in staleness_results],
            name="Approved Duration",
            orientation="h",
            marker_color=COLORS[0],
            opacity=0.6,
        )
    )

    # Actual Duration bars
    fig.add_trace(
        go.Bar(
            y=labels,
            x=[
                r.monthly_snapshots[-1].mean_duration if r.monthly_snapshots else 0
                for r in staleness_results
            ],
            name="Actual Mean Duration (Latest Month)",
            orientation="h",
            marker_color=[
                severity_colors.get(r.severity, "#999") for r in staleness_results
            ],
        )
    )

    # Suggested Duration markers
    fig.add_trace(
        go.Scatter(
            y=labels,
            x=[r.suggested_duration for r in staleness_results],
            name="Suggested Duration",
            mode="markers",
            marker=dict(symbol="diamond", size=12, color="#333", line=dict(width=1)),
        )
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Approved Duration vs Actual Performance (Staleness Assessment)",
        barmode="group",
        xaxis=dict(title="Duration (seconds)"),
        height=200 + 80 * len(staleness_results),
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return _save_chart(fig, output_dir, "chart_staleness_overview")


def chart_staleness_timeline(
    staleness_results: List,
    output_dir: str,
) -> str:
    """Line chart: group mean efficiency over time for each approved duration group.

    Shows the degradation trend that proves baselines are stale.

    Args:
        staleness_results: List of StalenessResult objects
        output_dir: Output directory

    Returns:
        Path to saved chart
    """
    if not staleness_results:
        return ""

    fig = go.Figure()

    for i, r in enumerate(staleness_results):
        if not r.monthly_snapshots:
            continue

        windows = [s.window for s in r.monthly_snapshots]
        effs = [s.group_mean_efficiency for s in r.monthly_snapshots]
        label = f"{r.target_duration}s ({r.severity})"

        fig.add_trace(
            go.Scatter(
                x=windows,
                y=effs,
                mode="lines+markers",
                name=label,
                line=dict(color=COLORS[i % len(COLORS)], width=2),
                marker=dict(size=4),
            )
        )

    fig.add_hline(
        y=0, line_dash="dash", line_color="#CCC", annotation_text="Target (0%)"
    )
    fig.add_hline(
        y=-15,
        line_dash="dot",
        line_color="#D4827E",
        annotation_text="Severe threshold (-15%)",
    )

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title="Efficiency Degradation Over Time by Part Group",
        yaxis=dict(title="Group Mean Efficiency %"),
        xaxis=dict(title="Month"),
        height=450,
        legend=dict(orientation="h", yanchor="bottom", y=1.02),
    )

    return _save_chart(fig, output_dir, "chart_efficiency_timeline")


# ==================== Shift Detection Chart ==================== #


def chart_hourly_shot_profile(
    detected_shifts,
    output_dir: str,
) -> str:
    """Bar chart: shots per hour with detected shift boundaries marked.

    Args:
        detected_shifts: DetectedShifts object
        output_dir: Output directory

    Returns:
        Path to saved chart
    """
    if not detected_shifts.hourly_shot_counts:
        return ""

    hours = [h for h, _ in detected_shifts.hourly_shot_counts]
    counts = [c for _, c in detected_shifts.hourly_shot_counts]

    # Color bars at boundary hours differently
    bar_colors = []
    for h in hours:
        if h in detected_shifts.boundaries:
            bar_colors.append(COLORS[2])  # tan for shift starts
        elif h in detected_shifts.dip_hours:
            bar_colors.append(COLORS[4])  # rose for dips
        else:
            bar_colors.append(COLORS[0])  # steel blue

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=hours,
            y=counts,
            marker_color=bar_colors,
            text=[f"{c:.2f}" for c in counts],
            textposition="outside",
            hovertemplate="Hour: %{x}:00<br>Relative Shot Rate: %{y:.3f}<extra></extra>",
        )
    )

    # Add vertical lines at detected boundaries
    for boundary in detected_shifts.boundaries:
        fig.add_vline(
            x=boundary - 0.5,
            line_dash="dash",
            line_color="#C05050",
            annotation_text=f"Shift @ {boundary:02d}:00",
            annotation_position="top",
        )

    conf_text = f"Confidence: {detected_shifts.confidence:.0%}"
    method_text = detected_shifts.method.replace("_", " ").title()

    fig.update_layout(
        **LAYOUT_DEFAULTS,
        title=f"Hourly Shot Rate Profile -- {method_text} ({conf_text})",
        xaxis=dict(title="Hour of Day", tickmode="linear", dtick=1),
        yaxis=dict(title="Normalized Shot Rate (0-1)"),
        height=400,
        showlegend=False,
    )

    return _save_chart(fig, output_dir, "chart_hourly_shot_profile")


# ==================== Generate All Charts ==================== #


def generate_all_charts(
    shift_analyses: List,
    tool_groups: List,
    windowed_groups: List,
    staleness_results: List,
    output_dir: str,
    detected_shifts=None,
) -> Dict[str, str]:
    """Generate all interactive charts and return paths.

    Args:
        shift_analyses: EquipmentShiftAnalysis list
        tool_groups: ApprovedCTGroup list
        windowed_groups: WindowedGroupResult list
        staleness_results: StalenessResult list
        output_dir: Output directory
        detected_shifts: DetectedShifts object (optional)

    Returns:
        Dict mapping chart name to file path
    """
    charts = {}

    if detected_shifts is not None:
        path = chart_hourly_shot_profile(detected_shifts, output_dir)
        if path:
            charts["hourly_profile"] = path

    path = chart_shift_variance(shift_analyses, output_dir)
    if path:
        charts["operator_variance"] = path

    path = chart_tool_comparison(tool_groups, output_dir)
    if path:
        charts["tool_comparison"] = path

    path = chart_tool_monthly_trend(windowed_groups, output_dir)
    if path:
        charts["monthly_trends"] = path

    path = chart_staleness_overview(staleness_results, output_dir)
    if path:
        charts["staleness_overview"] = path

    path = chart_staleness_timeline(staleness_results, output_dir)
    if path:
        charts["efficiency_timeline"] = path

    logger.info("Generated %d interactive charts", len(charts))
    return charts
