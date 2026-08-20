"""Consistent `st.dataframe` rendering for the dashboard.

Maps raw SQL column names onto human labels and number formats, hides the
meaningless index gutter, and bounds the height of long tables. Every table in
the app renders through `render_table` so a column appearing in two panels is
labelled identically in both.
"""

from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pandas as pd
import streamlit as st

# Bounded heights for tables that would otherwise render every row at full
# height inside an expander.
TABLE_HEIGHT_COMPACT: int = 240
TABLE_HEIGHT_STANDARD: int = 360

_PERCENT_FORMAT = "%.1f%%"
_DURATION_FORMAT = "%.2f"
_COUNT_FORMAT = "%d"

# Human labels for the raw SQL column names the queries return.
_LABELS: Dict[str, str] = {
    "MACHINE_ID": "Machine",
    "WEEK_START": "Week",
    "PERIOD": "Period",
    "SHOT_COUNT": "Shots",
    "SHOTS": "Shots",
    "TOTAL_SHOTS": "Shots",
    "AVG_DURATION": "Avg Duration (s)",
    "MIN_DURATION": "Min Duration (s)",
    "MAX_DURATION": "Max Duration (s)",
    "TARGET_DURATION": "Target (s)",
    "STD_DURATION": "Std Dev (s)",
    "DEVIATION_PCT": "Deviation",
    "STABILITY_SCORE": "Stability",
    "CV_PCT": "Variation",
    "EFFICIENCY_PCT": "Efficiency",
    "SEVERITY": "Severity",
    "FIRST_SHOT": "First Shot",
    "LAST_SHOT": "Last Shot",
    "TIMESTAMP": "Time",
    "ACTION_TYPE": "Action",
    "DESCRIPTION": "Description",
    "INITIATED_BY": "Initiated By",
    "TYPE": "Type",
    "ACCUMULATED_SHOTS": "Shots Used",
    "DESIGNED_SHOT": "Designed Life",
    "LIFE_USED_PCT": "Life Used",
    "REMAINING_PCT": "Remaining",
    "ORDER_TYPE": "Order Type",
    "COMPLETED_AT": "Completed",
    "AVG_BEFORE": "Avg Before (s)",
    "AVG_AFTER": "Avg After (s)",
    "CHANGE_PCT": "Change",
    "SHIFT_DATE": "Date",
    "AUTHOR_ROLE": "Role",
    "NOTE_TEXT": "Note",
    "TOTAL_NOTES": "Notes",
    "DRIFT_MENTIONS": "Drift",
    "FAULT_MENTIONS": "Faults",
    "MAINTENANCE_MENTIONS": "Maintenance",
    "SEQUENCE": "Step",
    "PHASE": "Phase",
    "TOOL_NAME": "Tool",
    "STEP_STATUS": "Status",
    "RESULT_SUMMARY": "Result",
    "PRODUCT_NAME": "Product",
    "AVG_DEVIATION": "Avg Deviation (s)",
    "CONTRIBUTION_PCT": "Contribution",
    "CUMULATIVE_PCT": "Cumulative",
    "AVG_ABS_DEVIATION": "Avg Abs Deviation (s)",
    "TOTAL_DEVIATION_SEC": "Total Deviation (s)",
    "HOUR_OF_DAY": "Hour",
    "DOW": "Day of Week",
}

_COUNT_COLUMNS = {
    "SHOT_COUNT",
    "SHOTS",
    "TOTAL_SHOTS",
    "ACCUMULATED_SHOTS",
    "DESIGNED_SHOT",
    "TOTAL_NOTES",
    "DRIFT_MENTIONS",
    "FAULT_MENTIONS",
    "MAINTENANCE_MENTIONS",
    "SEQUENCE",
}

_DURATION_COLUMNS = {
    "AVG_DURATION",
    "MIN_DURATION",
    "MAX_DURATION",
    "TARGET_DURATION",
    "STD_DURATION",
    "AVG_BEFORE",
    "AVG_AFTER",
    "AVG_DEVIATION",
    "AVG_ABS_DEVIATION",
    "TOTAL_DEVIATION_SEC",
}


def _supports_column_config() -> bool:
    """Report whether the runtime provides `st.column_config`.

    It landed in Streamlit 1.23 and the Streamlit-in-Snowflake runtime version
    is neither pinned nor verified, so callers fall back to a plain dataframe
    rather than risk an AttributeError.

    Returns:
        True when `st.column_config` is available.
    """
    return hasattr(st, "column_config")


def label_for(column: str) -> str:
    """Return the display label for a raw SQL column name.

    Args:
        column: The raw column name.

    Returns:
        The mapped label, or a title-cased fallback for unmapped columns.
    """
    if column in _LABELS:
        return _LABELS[column]
    return column.replace("_", " ").title()


@dataclass(frozen=True)
class ColumnSpec:
    """How one column should be presented.

    Attributes:
        label: Human-readable column header.
        number_format: printf-style format, or None for non-numeric columns.
    """

    label: str
    number_format: Optional[str]


def number_format_for(column: str) -> Optional[str]:
    """Return the printf-style number format for a column, if it is numeric.

    Args:
        column: The raw column name.

    Returns:
        A format string, or None when the column is not formatted as a number.
    """
    if column.endswith("_PCT") or column == "STABILITY_SCORE":
        return _PERCENT_FORMAT
    if column in _COUNT_COLUMNS:
        return _COUNT_FORMAT
    if column in _DURATION_COLUMNS:
        return _DURATION_FORMAT
    return None


def column_specs(columns: List[str]) -> Dict[str, ColumnSpec]:
    """Map column names to their presentation spec.

    Pure: no Streamlit involved, so the mapping rules stay testable independently
    of the runtime.

    Args:
        columns: Raw column names.

    Returns:
        A mapping of column name to `ColumnSpec`.
    """
    return {
        column: ColumnSpec(
            label=label_for(column), number_format=number_format_for(column)
        )
        for column in columns
    }


def build_column_config(df: pd.DataFrame) -> Dict[str, Any]:
    """Adapt `column_specs` into Streamlit column config objects.

    Args:
        df: The frame about to be rendered.

    Returns:
        A mapping of column name to a Streamlit column config object. Empty when
        the runtime does not support column configuration.
    """
    if not _supports_column_config():
        return {}

    config: Dict[str, Any] = {}
    for column, spec in column_specs(list(df.columns)).items():
        if spec.number_format is None:
            config[column] = st.column_config.Column(spec.label)
        else:
            config[column] = st.column_config.NumberColumn(
                spec.label, format=spec.number_format
            )
    return config


def render_table(
    df: pd.DataFrame,
    columns: Optional[List[str]] = None,
    height: Optional[int] = None,
) -> None:
    """Render a dataframe with shared labels, formats, and no index gutter.

    Args:
        df: The frame to render.
        columns: Optional explicit column subset and ordering.
        height: Optional fixed pixel height for long tables.
    """
    frame = df[columns] if columns else df

    kwargs: Dict[str, Any] = {"use_container_width": True}
    if height is not None:
        kwargs["height"] = height
    if _supports_column_config():
        kwargs["hide_index"] = True
        kwargs["column_config"] = build_column_config(frame)

    st.dataframe(frame, **kwargs)
