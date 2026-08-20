"""Reusable Altair chart builders shared across the dashboard panels.

Centralises the encodings that were previously copy-pasted -- the
status-coloured bar chart appeared five times in `analysis_panels` alone -- so
that axis formatting, heights, and tooltips stay consistent. Pure chart
construction only: these functions take a DataFrame and return an Altair object,
with no Streamlit or Snowflake calls.
"""

from typing import List, Optional, Sequence, Tuple

import altair as alt
import pandas as pd
from theme import (
    CHART_HEIGHT_SPARK,
    DATE_AXIS_FORMAT,
    DOMAIN_PADDING,
    PERCENT_AXIS_FORMAT,
    RULE_DASH,
    binary_status_scale,
)


def time_x(field: str, title: str) -> alt.X:
    """Build a time-typed x encoding with a short, readable date format.

    Args:
        field: Column name holding the timestamp.
        title: Axis title.

    Returns:
        A configured `alt.X` encoding.
    """
    return alt.X(f"{field}:T", title=title, axis=alt.Axis(format=DATE_AXIS_FORMAT))


def percent_y(
    field: str, title: str, domain: Optional[Sequence[float]] = None
) -> alt.Y:
    """Build a quantitative y encoding formatted as a percentage.

    Args:
        field: Column name holding the percentage value.
        title: Axis title.
        domain: Explicit [min, max]; when omitted Altair infers from the data.

    Returns:
        A configured `alt.Y` encoding.
    """
    axis = alt.Axis(format=PERCENT_AXIS_FORMAT, title=title)
    if domain is None:
        return alt.Y(f"{field}:Q", axis=axis)
    return alt.Y(f"{field}:Q", axis=axis, scale=alt.Scale(domain=list(domain)))


def padded_domain(values: pd.Series, floor: Optional[float] = None) -> Tuple[float, float]:
    """Derive an axis domain from data instead of hardcoding one.

    Hardcoded domains silently clip any series outside the range, which a live
    CSV ingest can easily produce.

    Args:
        values: The numeric series to be plotted.
        floor: Optional lower bound the domain must not go below.

    Returns:
        A (min, max) tuple padded by DOMAIN_PADDING of the value range.
    """
    low = float(values.min())
    high = float(values.max())
    span = high - low
    pad = span * DOMAIN_PADDING if span > 0 else max(abs(high) * DOMAIN_PADDING, 1.0)
    lower = low - pad
    if floor is not None:
        lower = max(lower, floor)
    return (lower, high + pad)


def status_bar_chart(
    df: pd.DataFrame,
    x: alt.X,
    y_field: str,
    y_title: str,
    tooltip: List[str],
    height: int = CHART_HEIGHT_SPARK,
    status_field: str = "STATUS",
) -> alt.Chart:
    """Build a bar chart coloured by a threshold status column.

    Args:
        df: Source data, already carrying `status_field`.
        x: A prepared x encoding.
        y_field: Column name for the bar height.
        y_title: Y axis title.
        tooltip: Tooltip field specifications.
        height: Chart height in pixels.
        status_field: Column holding the severity vocabulary value.

    Returns:
        A configured `alt.Chart` bar chart with the legend suppressed, since the
        colour restates the y value.
    """
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=x,
            y=alt.Y(f"{y_field}:Q", title=y_title),
            color=alt.Color(
                f"{status_field}:N", scale=binary_status_scale(), legend=None
            ),
            tooltip=tooltip,
        )
        .properties(height=height)
    )


def threshold_rule(value: float, label: str, color: str) -> alt.LayerChart:
    """Build a labelled horizontal threshold line.

    The label is drawn on the chart so the reader does not have to decode a
    colour key in a caption below it.

    Args:
        value: Y position of the rule.
        label: Text drawn at the left end of the rule.
        color: Rule and label colour.

    Returns:
        A layered rule-plus-text chart.
    """
    data = pd.DataFrame({"y": [value], "label": [label]})
    rule = (
        alt.Chart(data).mark_rule(strokeDash=RULE_DASH, color=color).encode(y="y:Q")
    )
    text = (
        alt.Chart(data)
        .mark_text(align="left", baseline="bottom", dx=4, dy=-3, fontSize=11)
        .encode(y="y:Q", x=alt.value(4), text="label:N", color=alt.value(color))
    )
    return rule + text
