"""Unit tests for the run_rate time_utils module.
Covers extract_time_dimensions, get_time_range_summary, and validate_time_dimensions
with happy-path, boundary, and error cases.
"""

from datetime import datetime

import pandas as pd
import pytest

from services.config.features.analytics.pipelines.run_rate.time_utils import (
    extract_time_dimensions,
    get_time_range_summary,
    validate_time_dimensions,
)

# ===================================================================
# extract_time_dimensions
# ===================================================================


class TestExtractTimeDimensions:
    """Tests for extract_time_dimensions."""

    def test_happy_path_adds_all_columns(self, raw_shot_df: pd.DataFrame) -> None:
        """All expected time columns are added."""
        result = extract_time_dimensions(raw_shot_df.copy())
        for col in ("DAY", "WEEK", "MONTH", "YEAR", "DATE"):
            assert col in result.columns

    def test_day_boundaries(self) -> None:
        """First and last day of a month are extracted correctly."""
        df = pd.DataFrame(
            {
                "LOCAL_SHOT_TIME": [
                    datetime(2025, 1, 1, 0, 0, 0),
                    datetime(2025, 1, 31, 23, 59, 59),
                ],
            }
        )
        result = extract_time_dimensions(df)
        assert result["DAY"].tolist() == [1, 31]
        assert result["MONTH"].tolist() == [1, 1]

    def test_iso_week_numbering(self) -> None:
        """ISO week for Jan 1 2025 is week 1 (Wednesday)."""
        df = pd.DataFrame(
            {
                "LOCAL_SHOT_TIME": [datetime(2025, 1, 1)],
            }
        )
        result = extract_time_dimensions(df)
        assert result["WEEK"].iloc[0] == 1

    def test_multi_year_span(self) -> None:
        """Correctly extracts YEAR across a year boundary."""
        df = pd.DataFrame(
            {
                "LOCAL_SHOT_TIME": [
                    datetime(2024, 12, 31, 23, 0, 0),
                    datetime(2025, 1, 1, 1, 0, 0),
                ],
            }
        )
        result = extract_time_dimensions(df)
        assert result["YEAR"].tolist() == [2024, 2025]

    def test_string_input_conversion(self) -> None:
        """String timestamps are converted to datetime before extraction."""
        df = pd.DataFrame(
            {
                "LOCAL_SHOT_TIME": ["2025-06-15 10:30:00", "2025-06-16 11:00:00"],
            }
        )
        result = extract_time_dimensions(df)
        assert result["DAY"].tolist() == [15, 16]
        assert result["MONTH"].tolist() == [6, 6]

    def test_preserves_existing_columns(self, raw_shot_df: pd.DataFrame) -> None:
        """Original columns survive after extraction."""
        df = raw_shot_df.copy()
        original_cols = set(df.columns)
        result = extract_time_dimensions(df)
        assert original_cols.issubset(set(result.columns))


# ===================================================================
# get_time_range_summary
# ===================================================================


class TestGetTimeRangeSummary:
    """Tests for get_time_range_summary."""

    def test_basic_summary(self, raw_shot_df: pd.DataFrame) -> None:
        """Summary contains all expected keys with sane values."""
        df = extract_time_dimensions(raw_shot_df.copy())
        summary = get_time_range_summary(df)
        assert "min_date" in summary
        assert "max_date" in summary
        assert "total_days" in summary
        assert summary["total_days"] >= 0
        assert summary["unique_dates"] >= 1

    def test_single_day(self) -> None:
        """Single-day dataset yields total_days == 0."""
        df = pd.DataFrame(
            {
                "LOCAL_SHOT_TIME": [
                    datetime(2025, 3, 10, 8, 0, 0),
                    datetime(2025, 3, 10, 9, 0, 0),
                ],
            }
        )
        df = extract_time_dimensions(df)
        summary = get_time_range_summary(df)
        assert summary["total_days"] == 0
        assert summary["unique_dates"] == 1

    def test_multi_month_span(self) -> None:
        """Multi-month data reports correct unique_months."""
        df = pd.DataFrame(
            {
                "LOCAL_SHOT_TIME": [
                    datetime(2025, 1, 15),
                    datetime(2025, 2, 15),
                    datetime(2025, 3, 15),
                ],
            }
        )
        df = extract_time_dimensions(df)
        summary = get_time_range_summary(df)
        assert summary["unique_months"] == 3
        assert summary["total_days"] == 59


# ===================================================================
# validate_time_dimensions
# ===================================================================


class TestValidateTimeDimensions:
    """Tests for validate_time_dimensions."""

    def test_valid_data_passes(self, raw_shot_df: pd.DataFrame) -> None:
        """Properly extracted dimensions pass validation."""
        df = extract_time_dimensions(raw_shot_df.copy())
        assert validate_time_dimensions(df) is True

    def test_missing_column_raises(self) -> None:
        """Raises ValueError when a required column is absent."""
        df = pd.DataFrame(
            {
                "DAY": [1],
                "WEEK": [1],
                "MONTH": [1],
                "YEAR": [2025],
                # DATE is missing
            }
        )
        with pytest.raises(ValueError, match="Missing time dimension columns"):
            validate_time_dimensions(df)

    def test_null_values_raise(self) -> None:
        """Raises ValueError when a time column has nulls."""
        df = pd.DataFrame(
            {
                "DAY": [1, None],
                "WEEK": [1, 1],
                "MONTH": [1, 1],
                "YEAR": [2025, 2025],
                "DATE": [datetime(2025, 1, 1).date(), datetime(2025, 1, 2).date()],
            }
        )
        with pytest.raises(ValueError, match="null values in DAY"):
            validate_time_dimensions(df)

    def test_day_out_of_range_raises(self) -> None:
        """Raises ValueError when DAY is outside 1-31."""
        df = pd.DataFrame(
            {
                "DAY": [0],
                "WEEK": [1],
                "MONTH": [1],
                "YEAR": [2025],
                "DATE": [datetime(2025, 1, 1).date()],
            }
        )
        with pytest.raises(ValueError, match="DAY column contains invalid values"):
            validate_time_dimensions(df)

    def test_month_out_of_range_raises(self) -> None:
        """Raises ValueError when MONTH is outside 1-12."""
        df = pd.DataFrame(
            {
                "DAY": [1],
                "WEEK": [1],
                "MONTH": [13],
                "YEAR": [2025],
                "DATE": [datetime(2025, 1, 1).date()],
            }
        )
        with pytest.raises(ValueError, match="MONTH column contains invalid values"):
            validate_time_dimensions(df)

    def test_week_out_of_range_raises(self) -> None:
        """Raises ValueError when WEEK is outside 1-53."""
        df = pd.DataFrame(
            {
                "DAY": [1],
                "WEEK": [54],
                "MONTH": [1],
                "YEAR": [2025],
                "DATE": [datetime(2025, 1, 1).date()],
            }
        )
        with pytest.raises(ValueError, match="WEEK column contains invalid values"):
            validate_time_dimensions(df)
