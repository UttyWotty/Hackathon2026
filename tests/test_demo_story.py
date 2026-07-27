"""
Tests for the demo's weekly drift aggregation.

Builds small in-memory shot frames and asserts the deviation maths, the shared
validity predicate, the low-volume week guard and the pivot for plotting. Pure
logic only: no CSV is read and no Snowflake is touched.
"""

from typing import List

import pandas as pd
import pytest

from demo.story import (
    COL_DEVIATION,
    COL_WEEK,
    MIN_SHOTS_PER_WEEK,
    StoryError,
    drift_magnitude,
    to_chart_frame,
    weekly_deviation,
)

EQUIPMENT = "EMA-4103"
PEER = "EMA-4101"
WEEK_ONE = "2026-06-08"
WEEK_TWO = "2026-06-15"


def _frame(rows: List[dict]) -> pd.DataFrame:
    """Build a MASTER_SHOT_TABLE-shaped frame from row dictionaries."""
    return pd.DataFrame(rows)


def _shots(
    equipment: str, day: str, ct: float, approved_ct: float, count: int
) -> List[dict]:
    """Repeat one shot shape count times on a given day."""
    return [
        {
            "EQUIPMENT_CODE": equipment,
            "LOCAL_SHOT_TIME": f"{day} 08:00:00",
            "CT": ct,
            "APPROVED_CT": approved_ct,
        }
        for _ in range(count)
    ]


def test_weekly_deviation_computes_percentage_above_approved():
    df = _frame(_shots(EQUIPMENT, WEEK_ONE, ct=11.0, approved_ct=10.0, count=100))
    weekly = weekly_deviation(df)
    assert len(weekly) == 1
    assert weekly[COL_DEVIATION].iloc[0] == pytest.approx(10.0)


def test_weekly_deviation_separates_weeks():
    df = _frame(
        _shots(EQUIPMENT, WEEK_ONE, 10.2, 10.0, 100)
        + _shots(EQUIPMENT, WEEK_TWO, 12.4, 10.0, 100)
    )
    weekly = weekly_deviation(df)
    assert len(weekly) == 2
    assert drift_magnitude(weekly, EQUIPMENT) == pytest.approx([2.0, 24.0])


def test_weekly_deviation_separates_machines():
    df = _frame(
        _shots(EQUIPMENT, WEEK_ONE, 12.4, 10.0, 100)
        + _shots(PEER, WEEK_ONE, 10.1, 10.0, 100)
    )
    weekly = weekly_deviation(df)
    assert set(weekly["EQUIPMENT_CODE"]) == {EQUIPMENT, PEER}
    assert drift_magnitude(weekly, PEER) == pytest.approx([1.0])


def test_weekly_deviation_drops_sentinel_cycle_times():
    """The chart applies the CT deviation predicate, so 999.9 never counts."""
    df = _frame(
        _shots(EQUIPMENT, WEEK_ONE, 11.0, 10.0, 100)
        + _shots(EQUIPMENT, WEEK_ONE, 999.9, 10.0, 100)
    )
    weekly = weekly_deviation(df)
    assert weekly[COL_DEVIATION].iloc[0] == pytest.approx(10.0)


def test_weekly_deviation_drops_a_week_below_the_shot_floor():
    df = _frame(
        _shots(EQUIPMENT, WEEK_ONE, 11.0, 10.0, MIN_SHOTS_PER_WEEK)
        + _shots(EQUIPMENT, WEEK_TWO, 50.0, 10.0, MIN_SHOTS_PER_WEEK - 1)
    )
    weekly = weekly_deviation(df)
    assert len(weekly) == 1
    assert weekly[COL_WEEK].iloc[0] == pd.Timestamp(WEEK_ONE)


def test_weekly_deviation_returns_an_empty_frame_for_empty_input():
    weekly = weekly_deviation(
        _frame([]).reindex(
            columns=["EQUIPMENT_CODE", "LOCAL_SHOT_TIME", "CT", "APPROVED_CT"]
        )
    )
    assert weekly.empty
    assert list(weekly.columns) == ["EQUIPMENT_CODE", COL_WEEK, COL_DEVIATION]


def test_weekly_deviation_rejects_a_frame_missing_a_column():
    with pytest.raises(StoryError):
        weekly_deviation(_frame([{"EQUIPMENT_CODE": EQUIPMENT}]))


def test_to_chart_frame_gives_one_column_per_machine():
    df = _frame(
        _shots(EQUIPMENT, WEEK_ONE, 11.0, 10.0, 100)
        + _shots(PEER, WEEK_ONE, 10.1, 10.0, 100)
    )
    chart = to_chart_frame(weekly_deviation(df))
    assert sorted(chart.columns) == [PEER, EQUIPMENT]
    assert len(chart) == 1


def test_to_chart_frame_handles_no_data():
    assert to_chart_frame(pd.DataFrame()).empty


def test_drift_magnitude_returns_empty_for_an_unknown_machine():
    df = _frame(_shots(EQUIPMENT, WEEK_ONE, 11.0, 10.0, 100))
    assert drift_magnitude(weekly_deviation(df), "EMA-9999") == []
