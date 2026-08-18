"""
Unit tests for the pareto_downtime module.
Covers calculate_real_downtime, detect_downtime_events, and calculate_downtime_statistics
with happy-path, boundary, and error cases.
All tests use in-memory DataFrames with no I/O.
"""

from datetime import datetime, timedelta
from typing import List

import pandas as pd

from analysis.rca.core_analysis.pareto_downtime import (
    DOWNTIME_GAP_THRESHOLD,
    INVALID_CT_THRESHOLD,
    calculate_downtime_statistics,
    calculate_real_downtime,
    detect_downtime_events,
)
from analysis.shared.constants import SessionDetection

# ===================================================================
# Helpers
# ===================================================================


def _make_shot_df(
    ct_values: List[float],
    gap_seconds: List[float],
    part: str = "PART_1",
    base_time: datetime = datetime(2025, 6, 1, 8, 0, 0),
) -> pd.DataFrame:
    """Build a shot DataFrame with explicit time gaps between shots.

    Args:
        ct_values: Duration for each shot.
        gap_seconds: Time gap to the *next* shot. Length must be len(ct_values)-1.
        part: Part name for all rows.
        base_time: Timestamp of the first shot.
    """
    assert len(gap_seconds) == len(ct_values) - 1
    n = len(ct_values)
    times = [base_time]
    for gap in gap_seconds:
        times.append(times[-1] + timedelta(seconds=gap))
    return pd.DataFrame(
        {
            "SHOT_TIME": pd.to_datetime(times),
            "DURATION": ct_values,
            "PRODUCT_NAME": [part] * n,
        }
    )


def _make_simple_df(
    ct_values: List[float],
    interval_seconds: float = 15.0,
    part: str = "PART_1",
    base_time: datetime = datetime(2025, 6, 1, 8, 0, 0),
) -> pd.DataFrame:
    """Build a shot DataFrame with uniform time intervals."""
    n = len(ct_values)
    gaps = [interval_seconds] * (n - 1)
    return _make_shot_df(ct_values, gaps, part=part, base_time=base_time)


# ===================================================================
# calculate_real_downtime
# ===================================================================


class TestCalculateRealDowntime:
    """Tests for calculate_real_downtime."""

    def test_happy_path_adds_columns(self) -> None:
        """Adds TIME_BETWEEN_SHOTS and DOWNTIME columns."""
        df = _make_simple_df([10.0, 10.0, 10.0])
        result = calculate_real_downtime(df)
        assert "TIME_BETWEEN_SHOTS" in result.columns
        assert "DOWNTIME" in result.columns

    def test_positive_downtime_recorded(self) -> None:
        """Downtime is recorded when time_between - prev_ct > 1."""
        ct_values = [10.0, 10.0]
        gap_seconds = [25.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[1] == 15.0

    def test_no_downtime_when_gap_equals_ct(self) -> None:
        """No downtime when time gap matches previous CT (within rounding)."""
        ct_values = [10.0, 10.0]
        gap_seconds = [10.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[1] == 0.0

    def test_rounding_errors_ignored(self) -> None:
        """Downtime of -1, 0, or 1 second is treated as rounding error."""
        ct_values = [10.0, 10.0, 10.0, 10.0]
        gap_seconds = [9.0, 10.0, 11.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].sum() == 0.0

    def test_invalid_ct_skipped(self) -> None:
        """Rows where previous DURATION >= 999 are skipped."""
        ct_values = [INVALID_CT_THRESHOLD, 10.0]
        gap_seconds = [500.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[1] == 0.0

    def test_session_break_skipped(self) -> None:
        """Gaps exceeding SESSION_GAP_SECONDS are skipped."""
        large_gap = SessionDetection.SESSION_GAP_SECONDS + 100
        ct_values = [10.0, 10.0]
        gap_seconds = [float(large_gap)]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[1] == 0.0

    def test_first_row_always_zero_downtime(self) -> None:
        """The first row always has 0.0 DOWNTIME (no previous shot)."""
        df = _make_simple_df([10.0, 10.0, 10.0])
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[0] == 0.0

    def test_negative_downtime_not_recorded(self) -> None:
        """Negative downtime (gap < CT) is not recorded."""
        ct_values = [20.0, 10.0]
        gap_seconds = [15.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[1] == 0.0

    def test_preserves_row_count(self) -> None:
        """Row count is unchanged after downtime calculation."""
        df = _make_simple_df([10.0] * 10)
        result = calculate_real_downtime(df)
        assert len(result) == 10

    def test_multiple_downtime_events(self) -> None:
        """Multiple downtime events are independently recorded."""
        ct_values = [10.0, 10.0, 10.0, 10.0]
        gap_seconds = [30.0, 10.0, 50.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result = calculate_real_downtime(df)
        assert result["DOWNTIME"].iloc[1] == 20.0
        assert result["DOWNTIME"].iloc[2] == 0.0
        assert result["DOWNTIME"].iloc[3] == 40.0


# ===================================================================
# detect_downtime_events
# ===================================================================


class TestDetectDowntimeEvents:
    """Tests for detect_downtime_events."""

    def test_happy_path_adds_columns(self) -> None:
        """Detection adds TIME_GAP_MINUTES, DOWNTIME_GAP_FLAG, DOWNTIME_CT_FLAG, DOWNTIME_EVENT."""
        df = _make_simple_df([10.0, 10.0, 10.0])
        result = detect_downtime_events(df)
        for col in [
            "TIME_GAP_MINUTES",
            "DOWNTIME_GAP_FLAG",
            "DOWNTIME_CT_FLAG",
            "DOWNTIME_EVENT",
        ]:
            assert col in result.columns

    def test_gap_based_detection(self) -> None:
        """A time gap exceeding gap_threshold minutes flags a downtime event."""
        gap_minutes = DOWNTIME_GAP_THRESHOLD + 1
        ct_values = [10.0, 10.0]
        gap_seconds = [gap_minutes * 60]
        df = _make_shot_df(ct_values, gap_seconds)
        result = detect_downtime_events(df)
        assert bool(result["DOWNTIME_GAP_FLAG"].iloc[1]) is True
        assert bool(result["DOWNTIME_EVENT"].iloc[1]) is True

    def test_ct_spike_detection(self) -> None:
        """A CT value exceeding ct_multiplier * median flags a downtime event."""
        ct_values = [10.0, 10.0, 10.0, 10.0, 10.0, 100.0]
        df = _make_simple_df(ct_values, interval_seconds=15.0)
        result = detect_downtime_events(df)
        spike_row = result[result["DURATION"] == 100.0]
        assert bool(spike_row["DOWNTIME_CT_FLAG"].iloc[0]) is True
        assert bool(spike_row["DOWNTIME_EVENT"].iloc[0]) is True

    def test_no_events_in_normal_data(self) -> None:
        """Normal data with short gaps and consistent CT has no downtime events."""
        ct_values = [10.0] * 10
        df = _make_simple_df(ct_values, interval_seconds=15.0)
        result = detect_downtime_events(df)
        assert result["DOWNTIME_GAP_FLAG"].sum() == 0

    def test_single_row_no_crash(self) -> None:
        """A DataFrame with fewer than 2 rows returns without events."""
        df = pd.DataFrame(
            {
                "SHOT_TIME": pd.to_datetime([datetime(2025, 6, 1, 8, 0, 0)]),
                "DURATION": [10.0],
            }
        )
        result = detect_downtime_events(df)
        assert len(result) == 1
        assert bool(result["DOWNTIME_EVENT"].iloc[0]) is False

    def test_custom_gap_threshold(self) -> None:
        """Custom gap_threshold changes detection sensitivity."""
        ct_values = [10.0, 10.0]
        gap_seconds = [180.0]
        df = _make_shot_df(ct_values, gap_seconds)
        result_strict = detect_downtime_events(df.copy(), gap_threshold=2.0)
        result_loose = detect_downtime_events(df.copy(), gap_threshold=10.0)
        assert bool(result_strict["DOWNTIME_GAP_FLAG"].iloc[1]) is True
        assert bool(result_loose["DOWNTIME_GAP_FLAG"].iloc[1]) is False

    def test_custom_ct_multiplier(self) -> None:
        """Custom ct_multiplier changes CT spike sensitivity."""
        ct_values = [10.0, 10.0, 10.0, 25.0]
        df = _make_simple_df(ct_values, interval_seconds=15.0)
        result_strict = detect_downtime_events(df.copy(), ct_multiplier=1.5)
        result_loose = detect_downtime_events(df.copy(), ct_multiplier=5.0)
        spike_strict = result_strict[result_strict["DURATION"] == 25.0]
        spike_loose = result_loose[result_loose["DURATION"] == 25.0]
        assert bool(spike_strict["DOWNTIME_CT_FLAG"].iloc[0]) is True
        assert bool(spike_loose["DOWNTIME_CT_FLAG"].iloc[0]) is False

    def test_combined_gap_and_ct_event(self) -> None:
        """A shot with both a large gap and CT spike is still one DOWNTIME_EVENT."""
        gap_minutes = DOWNTIME_GAP_THRESHOLD + 5
        ct_values = [10.0, 10.0, 10.0, 100.0]
        gap_seconds = [15.0, 15.0, gap_minutes * 60]
        df = _make_shot_df(ct_values, gap_seconds)
        result = detect_downtime_events(df)
        last = result.iloc[-1]
        assert bool(last["DOWNTIME_GAP_FLAG"]) is True
        assert bool(last["DOWNTIME_CT_FLAG"]) is True
        assert bool(last["DOWNTIME_EVENT"]) is True

    def test_preserves_row_count(self) -> None:
        """Row count is unchanged after detection."""
        df = _make_simple_df([10.0] * 10)
        result = detect_downtime_events(df)
        assert len(result) == 10


# ===================================================================
# calculate_downtime_statistics
# ===================================================================


class TestCalculateDowntimeStatistics:
    """Tests for calculate_downtime_statistics."""

    def _prepare_detected_df(
        self,
        ct_values: List[float],
        gap_seconds: List[float],
        part: str = "PART_1",
    ) -> pd.DataFrame:
        """Build a DataFrame that has already been through detect_downtime_events."""
        df = _make_shot_df(ct_values, gap_seconds, part=part)
        return detect_downtime_events(df)

    def test_returns_dataframe_with_product_name(self) -> None:
        """Returns a per-part downtime DataFrame when PRODUCT_NAME column exists."""
        ct_values = [10.0, 10.0, 10.0]
        gap_seconds = [15.0, 15.0]
        result_df = self._prepare_detected_df(ct_values, gap_seconds)
        stats = calculate_downtime_statistics(result_df)
        assert stats is not None
        assert isinstance(stats, pd.DataFrame)

    def test_returns_none_without_product_name(self) -> None:
        """Returns None when PRODUCT_NAME column is absent."""
        df = pd.DataFrame(
            {
                "SHOT_TIME": pd.to_datetime(
                    [
                        datetime(2025, 6, 1, 8, 0, 0),
                        datetime(2025, 6, 1, 8, 0, 15),
                    ]
                ),
                "DURATION": [10.0, 10.0],
            }
        )
        df = detect_downtime_events(df)
        stats = calculate_downtime_statistics(df)
        assert stats is None

    def test_stat_columns_in_result(self) -> None:
        """Result DataFrame has expected downtime stat columns."""
        ct_values = [10.0, 10.0, 10.0]
        gap_seconds = [15.0, 15.0]
        result_df = self._prepare_detected_df(ct_values, gap_seconds)
        stats = calculate_downtime_statistics(result_df)
        assert stats is not None
        expected_cols = [
            "Downtime_Events",
            "Total_Shots",
            "Avg_Gap_Min",
            "Max_Gap_Min",
            "Total_Idle_Min",
            "Downtime_Rate",
        ]
        for col in expected_cols:
            assert col in stats.columns, f"Missing column: {col}"

    def test_downtime_rate_calculation(self) -> None:
        """Downtime_Rate is (events / total_shots) * 100."""
        gap_minutes = DOWNTIME_GAP_THRESHOLD + 5
        ct_values = [10.0, 10.0, 10.0]
        gap_seconds = [gap_minutes * 60, gap_minutes * 60]
        result_df = self._prepare_detected_df(ct_values, gap_seconds)
        stats = calculate_downtime_statistics(result_df)
        assert stats is not None
        rate = stats["Downtime_Rate"].iloc[0]
        assert rate > 0

    def test_sorted_by_downtime_rate_descending(self) -> None:
        """Result is sorted by Downtime_Rate descending."""
        gap_big = (DOWNTIME_GAP_THRESHOLD + 10) * 60
        df1 = _make_shot_df([10.0, 10.0, 10.0], [15.0, 15.0], part="PART_LOW")
        df2 = _make_shot_df(
            [10.0, 10.0, 10.0],
            [gap_big, gap_big],
            part="PART_HIGH",
            base_time=datetime(2025, 6, 1, 12, 0, 0),
        )
        combined = pd.concat([df1, df2], ignore_index=True)
        combined = detect_downtime_events(combined)
        stats = calculate_downtime_statistics(combined)
        assert stats is not None
        rates = stats["Downtime_Rate"].tolist()
        assert rates == sorted(rates, reverse=True)

    def test_zero_events_zero_rate(self) -> None:
        """Part with no downtime events has zero downtime rate."""
        ct_values = [10.0] * 5
        result_df = self._prepare_detected_df(ct_values, [15.0, 15.0, 15.0, 15.0])
        stats = calculate_downtime_statistics(result_df)
        assert stats is not None
        assert stats["Downtime_Rate"].iloc[0] == 0.0
