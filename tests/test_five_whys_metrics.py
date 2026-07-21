"""
Unit tests for the five_whys_metrics module.
Covers calculate_basic_statistics, calculate_ct_metrics, calculate_scrap_metrics,
calculate_day_metrics, and related helper functions with happy-path, boundary,
and error cases.
All tests use in-memory DataFrames with no I/O.
"""

from typing import Dict, List

import pandas as pd

from analysis.rca.core_analysis.five_whys_metrics import (
    CT_ISSUE_DOWNTIME_MULTIPLIER,
    CT_ISSUE_SCRAP_RATE,
    calculate_basic_statistics,
    calculate_ct_metrics,
    calculate_day_metrics,
    calculate_downtime_metrics,
    calculate_efficiency_metrics,
    calculate_equipment_analysis,
    calculate_hour_analysis,
    calculate_scrap_from_column,
    calculate_scrap_from_ct_issues,
    calculate_scrap_from_ct_variance,
    calculate_scrap_metrics,
    calculate_scrap_rate,
    calculate_shift_analysis,
)

# ===================================================================
# Helpers
# ===================================================================


def _make_day_df(
    ct_values: List[float],
    ct_issue_flags: List[bool] = None,
    efficiency_values: List[float] = None,
    downtime_values: List[float] = None,
    scrap_values: List[int] = None,
    shifts: List[str] = None,
    hours: List[int] = None,
    equipment_codes: List[str] = None,
) -> pd.DataFrame:
    """Build a DataFrame representing a single day of shot data."""
    len(ct_values)
    data: Dict = {"CT": ct_values}
    if ct_issue_flags is not None:
        data["CT_ISSUE_FLAG"] = ct_issue_flags
    if efficiency_values is not None:
        data["EFFICIENCY"] = efficiency_values
    if downtime_values is not None:
        data["DOWNTIME"] = downtime_values
    if scrap_values is not None:
        data["SCRAP"] = scrap_values
    if shifts is not None:
        data["SHIFT"] = shifts
    if hours is not None:
        data["HOUR"] = hours
    if equipment_codes is not None:
        data["EQUIPMENT_CODE"] = equipment_codes
    return pd.DataFrame(data)


# ===================================================================
# calculate_basic_statistics
# ===================================================================


class TestCalculateBasicStatistics:
    """Tests for calculate_basic_statistics."""

    def test_happy_path(self) -> None:
        """Returns correct counts for both day and other days data."""
        day = _make_day_df([10.0, 12.0, 11.0])
        other = _make_day_df([9.0, 10.0])
        result = calculate_basic_statistics(day, other)
        assert result["day_count"] == 3
        assert result["other_days_count"] == 2

    def test_empty_day_data(self) -> None:
        """Returns zero count for empty day data."""
        day = _make_day_df([])
        other = _make_day_df([10.0])
        result = calculate_basic_statistics(day, other)
        assert result["day_count"] == 0
        assert result["other_days_count"] == 1

    def test_empty_other_data(self) -> None:
        """Returns zero count for empty comparison data."""
        day = _make_day_df([10.0, 11.0])
        other = _make_day_df([])
        result = calculate_basic_statistics(day, other)
        assert result["day_count"] == 2
        assert result["other_days_count"] == 0

    def test_both_empty(self) -> None:
        """Returns zero counts when both DataFrames are empty."""
        day = _make_day_df([])
        other = _make_day_df([])
        result = calculate_basic_statistics(day, other)
        assert result["day_count"] == 0
        assert result["other_days_count"] == 0


# ===================================================================
# calculate_ct_metrics
# ===================================================================


class TestCalculateCtMetrics:
    """Tests for calculate_ct_metrics."""

    def test_happy_path(self) -> None:
        """Returns average CT and variance for both groups."""
        day = _make_day_df([10.0, 12.0, 14.0])
        other = _make_day_df([9.0, 11.0, 13.0])
        result = calculate_ct_metrics(day, other)
        assert "avg_ct_day" in result
        assert "avg_ct_other" in result
        assert "ct_variance_day" in result
        assert "ct_variance_other" in result
        assert abs(result["avg_ct_day"] - 12.0) < 0.01

    def test_no_ct_column(self) -> None:
        """Returns empty dict when CT column is missing."""
        day = pd.DataFrame({"OTHER_COL": [1, 2, 3]})
        other = pd.DataFrame({"OTHER_COL": [4, 5]})
        result = calculate_ct_metrics(day, other)
        assert result == {}

    def test_empty_other_days(self) -> None:
        """Returns zero for other-days metrics when comparison data is empty."""
        day = _make_day_df([10.0, 12.0])
        other = _make_day_df([])
        result = calculate_ct_metrics(day, other)
        assert result["avg_ct_other"] == 0
        assert result["ct_variance_other"] == 0

    def test_single_row_variance_zero(self) -> None:
        """Variance is zero when day data has only one row."""
        day = _make_day_df([10.0])
        other = _make_day_df([12.0, 14.0])
        result = calculate_ct_metrics(day, other)
        assert result["ct_variance_day"] == 0

    def test_with_ct_issue_flag(self) -> None:
        """CT issue counts are calculated when CT_ISSUE_FLAG column exists."""
        day = _make_day_df([10.0, 12.0, 14.0], ct_issue_flags=[True, False, True])
        other = _make_day_df([9.0, 11.0], ct_issue_flags=[False, True])
        result = calculate_ct_metrics(day, other)
        assert result["ct_issues_day"] == 2
        assert result["ct_issues_other"] == 1

    def test_without_ct_issue_flag(self) -> None:
        """CT issue counts default to zero when CT_ISSUE_FLAG is absent."""
        day = _make_day_df([10.0, 12.0])
        other = _make_day_df([9.0])
        result = calculate_ct_metrics(day, other)
        assert result["ct_issues_day"] == 0
        assert result["ct_issues_other"] == 0


# ===================================================================
# calculate_scrap_rate
# ===================================================================


class TestCalculateScrapRate:
    """Tests for calculate_scrap_rate."""

    def test_happy_path(self) -> None:
        """Scrap rate is (scrap / total) * 100."""
        result = calculate_scrap_rate(5, 100)
        assert result == 5.0

    def test_zero_total_returns_zero(self) -> None:
        """Returns zero when total count is zero (no division error)."""
        result = calculate_scrap_rate(10, 0)
        assert result == 0.0

    def test_zero_scrap(self) -> None:
        """Returns zero when scrap count is zero."""
        result = calculate_scrap_rate(0, 100)
        assert result == 0.0

    def test_full_scrap(self) -> None:
        """Returns 100.0 when all parts are scrap."""
        result = calculate_scrap_rate(50, 50)
        assert result == 100.0


# ===================================================================
# calculate_scrap_metrics (dispatcher)
# ===================================================================


class TestCalculateScrapMetrics:
    """Tests for calculate_scrap_metrics dispatch logic."""

    def test_dispatches_to_column_method(self) -> None:
        """Uses SCRAP column when present."""
        day = _make_day_df([10.0, 12.0], scrap_values=[1, 0])
        other = _make_day_df([9.0, 11.0], scrap_values=[0, 1])
        result = calculate_scrap_metrics(day, other)
        assert "total_scrap_day" in result
        assert result["total_scrap_day"] == 1

    def test_dispatches_to_ct_issues_method(self) -> None:
        """Uses CT_ISSUE_FLAG when SCRAP column is absent."""
        day = _make_day_df([10.0, 12.0], ct_issue_flags=[True, False])
        other = _make_day_df([9.0], ct_issue_flags=[False])
        result = calculate_scrap_metrics(day, other)
        assert "estimated_scrap_day" in result

    def test_dispatches_to_ct_variance_method(self) -> None:
        """Falls back to CT variance when both SCRAP and CT_ISSUE_FLAG are absent."""
        day = _make_day_df([10.0, 12.0, 50.0, 10.0, 10.0])
        other = _make_day_df([9.0])
        result = calculate_scrap_metrics(day, other)
        assert "estimated_scrap_day" in result


# ===================================================================
# calculate_scrap_from_column
# ===================================================================


class TestCalculateScrapFromColumn:
    """Tests for calculate_scrap_from_column."""

    def test_happy_path(self) -> None:
        """Computes total scrap and scrap rate from SCRAP column."""
        day = _make_day_df([10.0, 12.0, 14.0], scrap_values=[1, 0, 2])
        other = _make_day_df([9.0, 11.0], scrap_values=[0, 1])
        result = calculate_scrap_from_column(day, other)
        assert result["total_scrap_day"] == 3
        assert result["total_scrap_other"] == 1
        assert abs(result["scrap_rate_day"] - 100.0) < 0.01

    def test_zero_scrap(self) -> None:
        """All zeros in SCRAP column yields zero rates."""
        day = _make_day_df([10.0, 12.0], scrap_values=[0, 0])
        other = _make_day_df([9.0], scrap_values=[0])
        result = calculate_scrap_from_column(day, other)
        assert result["scrap_rate_day"] == 0.0
        assert result["scrap_rate_other"] == 0.0


# ===================================================================
# calculate_scrap_from_ct_issues
# ===================================================================


class TestCalculateScrapFromCtIssues:
    """Tests for calculate_scrap_from_ct_issues."""

    def test_happy_path(self) -> None:
        """Estimated scrap equals CT_ISSUE_FLAG sum * CT_ISSUE_SCRAP_RATE."""
        day = _make_day_df(
            [10.0] * 20,
            ct_issue_flags=[True] * 10 + [False] * 10,
        )
        other = _make_day_df(
            [10.0] * 10,
            ct_issue_flags=[True] * 5 + [False] * 5,
        )
        result = calculate_scrap_from_ct_issues(day, other)
        assert result["estimated_scrap_day"] == int(10 * CT_ISSUE_SCRAP_RATE)
        assert result["estimated_scrap_other"] == int(5 * CT_ISSUE_SCRAP_RATE)

    def test_empty_other_days(self) -> None:
        """Empty other-days produces zero estimated scrap."""
        day = _make_day_df([10.0], ct_issue_flags=[True])
        other = _make_day_df([])
        other["CT_ISSUE_FLAG"] = pd.Series(dtype=bool)
        result = calculate_scrap_from_ct_issues(day, other)
        assert result["estimated_scrap_other"] == 0

    def test_no_issues_zero_scrap(self) -> None:
        """Zero CT issues yields zero estimated scrap."""
        day = _make_day_df([10.0, 12.0], ct_issue_flags=[False, False])
        other = _make_day_df([9.0], ct_issue_flags=[False])
        result = calculate_scrap_from_ct_issues(day, other)
        assert result["estimated_scrap_day"] == 0


# ===================================================================
# calculate_scrap_from_ct_variance
# ===================================================================


class TestCalculateScrapFromCtVariance:
    """Tests for calculate_scrap_from_ct_variance."""

    def test_happy_path(self) -> None:
        """Shots above mean + 2*std are counted as scrap events."""
        ct_values = [10.0] * 20 + [100.0]
        day = _make_day_df(ct_values)
        result = calculate_scrap_from_ct_variance(day)
        assert "estimated_scrap_day" in result
        assert "scrap_rate_day" in result

    def test_uniform_ct_no_scrap(self) -> None:
        """Uniform CT values produce no scrap events (std=0, threshold=mean)."""
        day = _make_day_df([10.0] * 10)
        result = calculate_scrap_from_ct_variance(day)
        assert result["estimated_scrap_day"] == 0


# ===================================================================
# calculate_day_metrics (aggregator)
# ===================================================================


class TestCalculateDayMetrics:
    """Tests for calculate_day_metrics."""

    def test_happy_path_all_keys(self) -> None:
        """Aggregated metrics contain basic, CT, and scrap keys."""
        day = _make_day_df(
            [10.0, 12.0, 14.0],
            ct_issue_flags=[True, False, True],
            efficiency_values=[85.0, 90.0, 80.0],
            downtime_values=[0.0, 5.0, 0.0],
            scrap_values=[1, 0, 0],
            shifts=["Day", "Day", "Night"],
            hours=[8, 9, 22],
            equipment_codes=["EQ_A", "EQ_A", "EQ_B"],
        )
        other = _make_day_df(
            [9.0, 11.0],
            ct_issue_flags=[False, True],
            efficiency_values=[88.0, 92.0],
            downtime_values=[0.0, 3.0],
            scrap_values=[0, 0],
            shifts=["Day", "Night"],
            hours=[8, 22],
            equipment_codes=["EQ_A", "EQ_B"],
        )
        result = calculate_day_metrics(day, other)
        assert "day_count" in result
        assert "other_days_count" in result
        assert "avg_ct_day" in result
        assert "avg_ct_other" in result

    def test_minimal_data(self) -> None:
        """Works with minimal CT-only DataFrames."""
        day = _make_day_df([10.0])
        other = _make_day_df([12.0])
        result = calculate_day_metrics(day, other)
        assert result["day_count"] == 1
        assert result["other_days_count"] == 1

    def test_includes_efficiency_when_present(self) -> None:
        """Efficiency metrics are included when EFFICIENCY column exists."""
        day = _make_day_df([10.0, 12.0], efficiency_values=[80.0, 90.0])
        other = _make_day_df([11.0], efficiency_values=[85.0])
        result = calculate_day_metrics(day, other)
        assert "avg_efficiency_day" in result
        assert abs(result["avg_efficiency_day"] - 85.0) < 0.01

    def test_includes_downtime_when_present(self) -> None:
        """Downtime metrics are included when DOWNTIME column exists."""
        day = _make_day_df([10.0, 12.0], downtime_values=[0.0, 5.0])
        other = _make_day_df([11.0], downtime_values=[3.0])
        result = calculate_day_metrics(day, other)
        assert "total_downtime_day" in result
        assert result["total_downtime_day"] == 5.0

    def test_includes_shift_analysis(self) -> None:
        """Shift analysis is included when SHIFT column exists."""
        day = _make_day_df(
            [10.0, 12.0, 14.0],
            shifts=["Day", "Day", "Night"],
        )
        other = _make_day_df([9.0])
        result = calculate_day_metrics(day, other)
        assert "shift_analysis" in result

    def test_includes_hour_analysis(self) -> None:
        """Hour analysis is included when HOUR column exists."""
        day = _make_day_df([10.0, 12.0], hours=[8, 9])
        other = _make_day_df([9.0])
        result = calculate_day_metrics(day, other)
        assert "hour_analysis" in result

    def test_includes_equipment_analysis(self) -> None:
        """Equipment analysis is included when EQUIPMENT_CODE column exists."""
        day = _make_day_df([10.0, 12.0], equipment_codes=["EQ_A", "EQ_B"])
        other = _make_day_df([9.0])
        result = calculate_day_metrics(day, other)
        assert "equipment_analysis" in result

    def test_missing_optional_columns_no_crash(self) -> None:
        """Missing optional columns (EFFICIENCY, SHIFT, HOUR, etc.) do not crash."""
        day = _make_day_df([10.0, 12.0, 50.0, 10.0, 10.0])
        other = _make_day_df([9.0])
        result = calculate_day_metrics(day, other)
        assert "day_count" in result
        assert "shift_analysis" not in result
        assert "hour_analysis" not in result
        assert "equipment_analysis" not in result


# ===================================================================
# calculate_efficiency_metrics
# ===================================================================


class TestCalculateEfficiencyMetrics:
    """Tests for calculate_efficiency_metrics."""

    def test_happy_path(self) -> None:
        """Returns average efficiency for both groups."""
        day = _make_day_df([10.0], efficiency_values=[85.0])
        other = _make_day_df([10.0], efficiency_values=[90.0])
        result = calculate_efficiency_metrics(day, other)
        assert result["avg_efficiency_day"] == 85.0
        assert result["avg_efficiency_other"] == 90.0

    def test_no_efficiency_column(self) -> None:
        """Returns empty dict when EFFICIENCY column is missing."""
        day = _make_day_df([10.0])
        other = _make_day_df([10.0])
        result = calculate_efficiency_metrics(day, other)
        assert result == {}

    def test_empty_other_days(self) -> None:
        """Returns zero efficiency for other days when empty."""
        day = _make_day_df([10.0], efficiency_values=[85.0])
        other = pd.DataFrame(
            {"CT": pd.Series(dtype=float), "EFFICIENCY": pd.Series(dtype=float)}
        )
        result = calculate_efficiency_metrics(day, other)
        assert result["avg_efficiency_other"] == 0


# ===================================================================
# calculate_downtime_metrics
# ===================================================================


class TestCalculateDowntimeMetrics:
    """Tests for calculate_downtime_metrics."""

    def test_with_downtime_column(self) -> None:
        """Uses DOWNTIME column directly when available."""
        day = _make_day_df([10.0, 12.0], downtime_values=[0.0, 5.0])
        other = _make_day_df([11.0], downtime_values=[3.0])
        result = calculate_downtime_metrics(day, other)
        assert result["total_downtime_day"] == 5.0
        assert result["total_downtime_other"] == 3.0
        assert result["avg_downtime_day"] == 2.5

    def test_estimated_from_ct_issue_flag(self) -> None:
        """Estimates downtime from CT_ISSUE_FLAG when DOWNTIME column is absent."""
        day = _make_day_df(
            [10.0, 12.0, 14.0],
            ct_issue_flags=[True, True, False],
        )
        other = _make_day_df([9.0], ct_issue_flags=[True])
        result = calculate_downtime_metrics(day, other)
        assert result["estimated_downtime_day"] == 2 * CT_ISSUE_DOWNTIME_MULTIPLIER
        assert result["estimated_downtime_other"] == 1 * CT_ISSUE_DOWNTIME_MULTIPLIER

    def test_estimated_from_ct_variance(self) -> None:
        """Falls back to CT variance estimation when no flag columns exist."""
        day = _make_day_df([10.0, 10.0, 10.0, 10.0, 100.0])
        other = _make_day_df([10.0])
        result = calculate_downtime_metrics(day, other)
        assert "estimated_downtime_day" in result

    def test_empty_other_days_with_downtime(self) -> None:
        """Returns zero for other-days downtime when comparison data is empty."""
        day = _make_day_df([10.0], downtime_values=[5.0])
        other = pd.DataFrame(
            {"CT": pd.Series(dtype=float), "DOWNTIME": pd.Series(dtype=float)}
        )
        result = calculate_downtime_metrics(day, other)
        assert result["total_downtime_other"] == 0


# ===================================================================
# calculate_shift_analysis
# ===================================================================


class TestCalculateShiftAnalysis:
    """Tests for calculate_shift_analysis."""

    def test_happy_path(self) -> None:
        """Returns shift_analysis key with grouped data."""
        day = _make_day_df(
            [10.0, 12.0, 14.0, 11.0],
            shifts=["Day", "Day", "Night", "Night"],
        )
        result = calculate_shift_analysis(day)
        assert "shift_analysis" in result

    def test_no_shift_column(self) -> None:
        """Returns empty dict when SHIFT column is missing."""
        day = _make_day_df([10.0, 12.0])
        result = calculate_shift_analysis(day)
        assert result == {}

    def test_with_ct_issue_flag(self) -> None:
        """Includes CT_ISSUE_FLAG aggregation when column exists."""
        day = _make_day_df(
            [10.0, 12.0],
            ct_issue_flags=[True, False],
            shifts=["Day", "Day"],
        )
        result = calculate_shift_analysis(day)
        assert "shift_analysis" in result


# ===================================================================
# calculate_hour_analysis
# ===================================================================


class TestCalculateHourAnalysis:
    """Tests for calculate_hour_analysis."""

    def test_happy_path(self) -> None:
        """Returns hour_analysis key with grouped data."""
        day = _make_day_df([10.0, 12.0, 14.0], hours=[8, 9, 10])
        result = calculate_hour_analysis(day)
        assert "hour_analysis" in result

    def test_no_hour_column(self) -> None:
        """Returns empty dict when HOUR column is missing."""
        day = _make_day_df([10.0])
        result = calculate_hour_analysis(day)
        assert result == {}


# ===================================================================
# calculate_equipment_analysis
# ===================================================================


class TestCalculateEquipmentAnalysis:
    """Tests for calculate_equipment_analysis."""

    def test_happy_path(self) -> None:
        """Returns equipment_analysis key with grouped data."""
        day = _make_day_df(
            [10.0, 12.0, 14.0],
            equipment_codes=["EQ_A", "EQ_A", "EQ_B"],
        )
        result = calculate_equipment_analysis(day)
        assert "equipment_analysis" in result

    def test_no_equipment_column(self) -> None:
        """Returns empty dict when EQUIPMENT_CODE column is missing."""
        day = _make_day_df([10.0])
        result = calculate_equipment_analysis(day)
        assert result == {}

    def test_with_ct_issue_flag(self) -> None:
        """Includes CT_ISSUE_FLAG aggregation when column exists."""
        day = _make_day_df(
            [10.0, 12.0],
            ct_issue_flags=[True, False],
            equipment_codes=["EQ_A", "EQ_B"],
        )
        result = calculate_equipment_analysis(day)
        assert "equipment_analysis" in result
