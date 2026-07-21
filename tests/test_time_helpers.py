"""
Tests for RunRate time formatting helper functions.

Verifies format_time_readable (minutes input) and format_time_readable_seconds
(seconds input) produce correct human-readable strings. Covers zero, NaN,
sub-minute, multi-minute, and multi-hour inputs along with boundary cases.
"""

import pandas as pd

from analysis.runrate.utils.time_helpers import (
    format_time_readable,
    format_time_readable_seconds,
)

# ---------------------------------------------------------------------------
# format_time_readable (input in minutes)
# ---------------------------------------------------------------------------


class TestFormatTimeReadableZeroAndNaN:
    """Tests for zero and NaN inputs to format_time_readable."""

    def test_zero_returns_zero_sec(self) -> None:
        """Zero minutes returns '0 sec'."""
        assert format_time_readable(0) == "0 sec"

    def test_zero_float_returns_zero_sec(self) -> None:
        """Zero as float returns '0 sec'."""
        assert format_time_readable(0.0) == "0 sec"

    def test_nan_returns_zero_sec(self) -> None:
        """NaN input returns '0 sec'."""
        assert format_time_readable(float("nan")) == "0 sec"

    def test_pandas_nan_returns_zero_sec(self) -> None:
        """pandas NaN (pd.NA equivalent via np) returns '0 sec'."""
        assert format_time_readable(pd.NaT) == "0 sec"


class TestFormatTimeReadableSecondsOnly:
    """Tests for sub-minute values in format_time_readable."""

    def test_half_minute(self) -> None:
        """0.5 minutes (30 seconds) formats as seconds only."""
        assert format_time_readable(0.5) == "30 sec"

    def test_quarter_minute(self) -> None:
        """0.25 minutes (15 seconds) formats as seconds only."""
        assert format_time_readable(0.25) == "15 sec"

    def test_small_fraction(self) -> None:
        """Very small fraction produces seconds-only output."""
        result = format_time_readable(0.1)  # 6 seconds
        assert result == "6 sec"

    def test_nearly_one_minute(self) -> None:
        """0.99 minutes stays in seconds-only format (59 sec)."""
        result = format_time_readable(0.99)  # 59.4 sec -> int(59) = 59
        assert "sec" in result
        assert "min" not in result


class TestFormatTimeReadableMinutesAndSeconds:
    """Tests for values in the minutes range for format_time_readable."""

    def test_exact_one_minute(self) -> None:
        """1.0 minute formats as '1 min 0 sec'."""
        assert format_time_readable(1.0) == "1 min 0 sec"

    def test_one_and_half_minutes(self) -> None:
        """1.5 minutes formats as '1 min 30 sec'."""
        assert format_time_readable(1.5) == "1 min 30 sec"

    def test_five_minutes(self) -> None:
        """5.0 minutes formats as '5 min 0 sec'."""
        assert format_time_readable(5.0) == "5 min 0 sec"

    def test_ten_minutes_thirty_seconds(self) -> None:
        """10.5 minutes formats as '10 min 30 sec'."""
        assert format_time_readable(10.5) == "10 min 30 sec"

    def test_fifty_nine_minutes(self) -> None:
        """59.0 minutes formats as '59 min 0 sec'."""
        assert format_time_readable(59.0) == "59 min 0 sec"


class TestFormatTimeReadableHours:
    """Tests for values in the hours range for format_time_readable."""

    def test_exactly_one_hour(self) -> None:
        """60.0 minutes formats as '1h 0m 0s'."""
        assert format_time_readable(60.0) == "1h 0m 0s"

    def test_one_hour_five_minutes(self) -> None:
        """65.0 minutes formats as '1h 5m 0s'."""
        assert format_time_readable(65.0) == "1h 5m 0s"

    def test_two_hours_five_minutes(self) -> None:
        """125.0 minutes formats as '2h 5m 0s'."""
        assert format_time_readable(125.0) == "2h 5m 0s"

    def test_two_hours_thirty_minutes(self) -> None:
        """150.0 minutes formats as '2h 30m 0s'."""
        assert format_time_readable(150.0) == "2h 30m 0s"

    def test_twenty_four_hours(self) -> None:
        """1440.0 minutes (24 hours) formats correctly."""
        assert format_time_readable(1440.0) == "24h 0m 0s"

    def test_hour_with_seconds(self) -> None:
        """60.5 minutes formats as '1h 0m 30s'."""
        assert format_time_readable(60.5) == "1h 0m 30s"


class TestFormatTimeReadableBoundary:
    """Boundary tests for format_time_readable at format transitions."""

    def test_boundary_just_under_one_minute(self) -> None:
        """Value just under 1 minute uses seconds-only format."""
        result = format_time_readable(59.0 / 60.0)  # 59 seconds
        assert "min" not in result
        assert "sec" in result

    def test_boundary_at_one_minute(self) -> None:
        """Value at exactly 1 minute uses minutes format."""
        result = format_time_readable(1.0)
        assert "min" in result

    def test_boundary_just_under_one_hour(self) -> None:
        """59.99 minutes uses minutes format, not hours."""
        result = format_time_readable(59.99)
        assert "min" in result
        assert "h" not in result

    def test_boundary_at_one_hour(self) -> None:
        """60.0 minutes uses hours format."""
        result = format_time_readable(60.0)
        assert "h" in result


class TestFormatTimeReadableReturnType:
    """Tests verifying the return type of format_time_readable."""

    def test_returns_string(self) -> None:
        """Function always returns a string."""
        assert isinstance(format_time_readable(0), str)
        assert isinstance(format_time_readable(1.5), str)
        assert isinstance(format_time_readable(120.0), str)
        assert isinstance(format_time_readable(float("nan")), str)


# ---------------------------------------------------------------------------
# format_time_readable_seconds (input in seconds)
# ---------------------------------------------------------------------------


class TestFormatTimeReadableSecondsZeroAndNaN:
    """Tests for zero and NaN inputs to format_time_readable_seconds."""

    def test_zero_returns_zero_sec(self) -> None:
        """Zero seconds returns '0 sec'."""
        assert format_time_readable_seconds(0) == "0 sec"

    def test_zero_float_returns_zero_sec(self) -> None:
        """Zero as float returns '0 sec'."""
        assert format_time_readable_seconds(0.0) == "0 sec"

    def test_nan_returns_zero_sec(self) -> None:
        """NaN input returns '0 sec'."""
        assert format_time_readable_seconds(float("nan")) == "0 sec"

    def test_pandas_nat_returns_zero_sec(self) -> None:
        """pandas NaT returns '0 sec'."""
        assert format_time_readable_seconds(pd.NaT) == "0 sec"


class TestFormatTimeReadableSecondsSecondsOnly:
    """Tests for sub-minute values in format_time_readable_seconds."""

    def test_one_second(self) -> None:
        """1 second formats as '1 sec'."""
        assert format_time_readable_seconds(1.0) == "1 sec"

    def test_thirty_seconds(self) -> None:
        """30 seconds formats as '30 sec'."""
        assert format_time_readable_seconds(30.0) == "30 sec"

    def test_forty_five_seconds(self) -> None:
        """45 seconds formats as '45 sec'."""
        assert format_time_readable_seconds(45.0) == "45 sec"

    def test_fifty_nine_seconds(self) -> None:
        """59 seconds formats as '59 sec'."""
        assert format_time_readable_seconds(59.0) == "59 sec"

    def test_fractional_seconds_truncated(self) -> None:
        """Fractional seconds are truncated to integer."""
        result = format_time_readable_seconds(45.7)
        assert result == "45 sec"


class TestFormatTimeReadableSecondsMinutes:
    """Tests for values in the minutes range for format_time_readable_seconds."""

    def test_exactly_one_minute(self) -> None:
        """60 seconds formats as '1 min 0 sec'."""
        assert format_time_readable_seconds(60.0) == "1 min 0 sec"

    def test_ninety_seconds(self) -> None:
        """90 seconds formats as '1 min 30 sec'."""
        assert format_time_readable_seconds(90.0) == "1 min 30 sec"

    def test_ninety_five_seconds(self) -> None:
        """95 seconds formats as '1 min 35 sec'."""
        assert format_time_readable_seconds(95.0) == "1 min 35 sec"

    def test_ninety_five_point_five_seconds(self) -> None:
        """95.5 seconds formats as '1 min 35 sec' (truncated)."""
        assert format_time_readable_seconds(95.5) == "1 min 35 sec"

    def test_five_minutes(self) -> None:
        """300 seconds formats as '5 min 0 sec'."""
        assert format_time_readable_seconds(300.0) == "5 min 0 sec"

    def test_fifty_nine_minutes(self) -> None:
        """3540 seconds (59 min) formats as '59 min 0 sec'."""
        assert format_time_readable_seconds(3540.0) == "59 min 0 sec"


class TestFormatTimeReadableSecondsHours:
    """Tests for values in the hours range for format_time_readable_seconds."""

    def test_exactly_one_hour(self) -> None:
        """3600 seconds formats as '1h 0m 0s'."""
        assert format_time_readable_seconds(3600.0) == "1h 0m 0s"

    def test_one_hour_one_minute(self) -> None:
        """3660 seconds formats as '1h 1m 0s'."""
        assert format_time_readable_seconds(3660.0) == "1h 1m 0s"

    def test_one_hour_thirty_minutes(self) -> None:
        """5400 seconds formats as '1h 30m 0s'."""
        assert format_time_readable_seconds(5400.0) == "1h 30m 0s"

    def test_two_hours(self) -> None:
        """7200 seconds formats as '2h 0m 0s'."""
        assert format_time_readable_seconds(7200.0) == "2h 0m 0s"

    def test_large_value_twenty_four_hours(self) -> None:
        """86400 seconds (24 hours) formats correctly."""
        assert format_time_readable_seconds(86400.0) == "24h 0m 0s"

    def test_hour_with_minutes_and_seconds(self) -> None:
        """3661 seconds formats as '1h 1m 1s'."""
        assert format_time_readable_seconds(3661.0) == "1h 1m 1s"


class TestFormatTimeReadableSecondsBoundary:
    """Boundary tests for format_time_readable_seconds at format transitions."""

    def test_boundary_just_under_one_minute(self) -> None:
        """59 seconds uses seconds-only format."""
        result = format_time_readable_seconds(59.0)
        assert "min" not in result
        assert "sec" in result

    def test_boundary_at_one_minute(self) -> None:
        """60 seconds uses minutes format."""
        result = format_time_readable_seconds(60.0)
        assert "min" in result

    def test_boundary_just_under_one_hour(self) -> None:
        """3599 seconds uses minutes format, not hours."""
        result = format_time_readable_seconds(3599.0)
        assert "min" in result
        assert "h" not in result

    def test_boundary_at_one_hour(self) -> None:
        """3600 seconds uses hours format."""
        result = format_time_readable_seconds(3600.0)
        assert "h" in result


class TestFormatTimeReadableSecondsReturnType:
    """Tests verifying the return type of format_time_readable_seconds."""

    def test_returns_string(self) -> None:
        """Function always returns a string."""
        assert isinstance(format_time_readable_seconds(0), str)
        assert isinstance(format_time_readable_seconds(95.0), str)
        assert isinstance(format_time_readable_seconds(3600.0), str)
        assert isinstance(format_time_readable_seconds(float("nan")), str)


class TestFormatTimeConsistency:
    """Cross-function consistency tests between both formatters."""

    def test_same_output_for_equivalent_inputs(self) -> None:
        """1.5 minutes and 90 seconds produce the same output."""
        from_minutes = format_time_readable(1.5)
        from_seconds = format_time_readable_seconds(90.0)
        assert from_minutes == from_seconds

    def test_zero_consistency(self) -> None:
        """Both functions return '0 sec' for zero input."""
        assert format_time_readable(0) == format_time_readable_seconds(0)

    def test_one_hour_consistency(self) -> None:
        """60 minutes and 3600 seconds produce the same output."""
        from_minutes = format_time_readable(60.0)
        from_seconds = format_time_readable_seconds(3600.0)
        assert from_minutes == from_seconds

    def test_two_hours_five_minutes_consistency(self) -> None:
        """125 minutes and 7500 seconds produce the same output."""
        from_minutes = format_time_readable(125.0)
        from_seconds = format_time_readable_seconds(7500.0)
        assert from_minutes == from_seconds

    def test_thirty_seconds_consistency(self) -> None:
        """0.5 minutes and 30 seconds produce the same output."""
        from_minutes = format_time_readable(0.5)
        from_seconds = format_time_readable_seconds(30.0)
        assert from_minutes == from_seconds
