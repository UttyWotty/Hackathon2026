"""
Pure aggregation of shot data into the week-by-week drift story.

Computes per-equipment cycle time deviation against approved CT, bucketed by
week, which is the view that makes the headline defect visible: one machine
climbing while the fleet stays flat. Takes a DataFrame and returns a DataFrame,
so all file access stays in analysis.shared.local_source.
"""

from typing import List

import pandas as pd

from analysis.shared.shot_filters import (
    COL_APPROVED_CT,
    COL_CT,
    COL_EQUIPMENT,
    COL_SHOT_TIME,
    apply_validity_filter,
)

# Output column names, shared by the chart and its tests.
COL_WEEK = "week_start"
COL_DEVIATION = "deviation_pct"

# Weekly buckets starting on Monday, matching the generator's window start and
# its five production days a week. Pandas names a weekly period by the day it
# ENDS on, so the Monday-to-Sunday week is "W-SUN"; "W-MON" would shift every
# bucket back by a day and split a production week across two points.
WEEK_FREQUENCY = "W-SUN"

PERCENT = 100.0

# A machine needs at least this many valid shots in a week for that week's
# mean to mean anything. Below it the bucket is dropped rather than plotted,
# because a handful of shots produces a spike that reads as a real excursion.
MIN_SHOTS_PER_WEEK = 50


class StoryError(Exception):
    """Raised when the drift story cannot be computed from the given shots."""


def _require_columns(df: pd.DataFrame) -> None:
    """Fail loudly when the frame is missing a column the story needs."""
    required = (COL_EQUIPMENT, COL_SHOT_TIME, COL_CT, COL_APPROVED_CT)
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise StoryError(f"Shot data is missing columns: {', '.join(missing)}")


def weekly_deviation(df: pd.DataFrame) -> pd.DataFrame:
    """
    Compute mean CT deviation against approved CT, per equipment per week.

    Applies the same validity predicate as the CT deviation analysis, so the
    chart and the agent's own sense tools agree on which shots count.

    Args:
        df: Raw MASTER_SHOT_TABLE rows.

    Returns:
        A long frame with equipment, week_start and deviation_pct, sorted by
        equipment then week. Empty input yields an empty frame with those
        columns.

    Raises:
        StoryError: If a required column is absent.
    """
    _require_columns(df)
    columns = [COL_EQUIPMENT, COL_WEEK, COL_DEVIATION]
    if df.empty:
        return pd.DataFrame(columns=columns)

    valid = apply_validity_filter(df).copy()
    if valid.empty:
        return pd.DataFrame(columns=columns)

    valid[COL_SHOT_TIME] = pd.to_datetime(valid[COL_SHOT_TIME])
    valid[COL_DEVIATION] = (
        (valid[COL_CT] - valid[COL_APPROVED_CT]) / valid[COL_APPROVED_CT] * PERCENT
    )
    valid[COL_WEEK] = valid[COL_SHOT_TIME].dt.to_period(WEEK_FREQUENCY).dt.start_time

    grouped = valid.groupby([COL_EQUIPMENT, COL_WEEK], as_index=False).agg(
        deviation_pct=(COL_DEVIATION, "mean"),
        shot_count=(COL_DEVIATION, "size"),
    )
    kept = grouped[grouped["shot_count"] >= MIN_SHOTS_PER_WEEK]
    return kept[columns].sort_values([COL_EQUIPMENT, COL_WEEK]).reset_index(drop=True)


def to_chart_frame(weekly: pd.DataFrame) -> pd.DataFrame:
    """
    Pivot the long weekly frame into one column per machine for plotting.

    Args:
        weekly: The output of weekly_deviation.

    Returns:
        A frame indexed by week_start with one column per equipment code.
    """
    if weekly.empty:
        return pd.DataFrame()
    return weekly.pivot(
        index=COL_WEEK, columns=COL_EQUIPMENT, values=COL_DEVIATION
    ).sort_index()


def drift_magnitude(weekly: pd.DataFrame, equipment_code: str) -> List[float]:
    """
    Return one machine's weekly deviation series, oldest week first.

    Args:
        weekly: The output of weekly_deviation.
        equipment_code: The machine to extract.

    Returns:
        Deviation percentages in week order; empty if the machine is absent.
    """
    if weekly.empty:
        return []
    rows = weekly[weekly[COL_EQUIPMENT] == equipment_code].sort_values(COL_WEEK)
    return [float(value) for value in rows[COL_DEVIATION]]


__all__ = [
    "StoryError",
    "weekly_deviation",
    "to_chart_frame",
    "drift_magnitude",
    "COL_WEEK",
    "COL_DEVIATION",
]
