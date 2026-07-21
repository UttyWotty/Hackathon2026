"""Unit tests for the run_rate calculations module.
Covers calculate_mode_ct, detect_stops, calculate_run_efficiency,
calculate_weighted_efficiency, MTTR/MTBF helpers, calculate_stop_metrics,
and validate_calculations with happy-path, boundary, and error cases.
"""

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from services.config.features.analytics.pipelines.run_rate.calculations import (
    _calculate_mtbf,
    _calculate_mttr,
    calculate_mode_ct,
    calculate_run_efficiency,
    calculate_stop_metrics,
    calculate_weighted_efficiency,
    detect_stops,
    validate_calculations,
)

MAX_CT_THRESHOLD = 999.9


# ===================================================================
# Helpers
# ===================================================================


def _make_session_df(
    ct_values: list,
    session_id: int = 1,
    equipment: str = "EQ_A",
    base_time: datetime = datetime(2025, 6, 1, 8, 0, 0),
) -> pd.DataFrame:
    """Build a minimal sessioned DataFrame from a list of CT values."""
    n = len(ct_values)
    times = [base_time + timedelta(seconds=i * 10) for i in range(n)]
    df = pd.DataFrame(
        {
            "EQUIPMENT_CODE": [equipment] * n,
            "LOCAL_SHOT_TIME": pd.to_datetime(times),
            "CT": ct_values,
            "SESSION_ID": [session_id] * n,
        }
    )
    # Calculate SHOT_DIFF_SEC (first is None)
    df["SHOT_DIFF_SEC"] = df["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
    df.loc[df.index[0], "SHOT_DIFF_SEC"] = None
    return df


# ===================================================================
# calculate_mode_ct
# ===================================================================


class TestCalculateModeCt:
    """Tests for calculate_mode_ct."""

    def test_happy_path(self) -> None:
        """Mode CT is the most frequent CT value in the session."""
        df = _make_session_df([10.0, 10.0, 10.0, 12.0, 12.0])
        result = calculate_mode_ct(df)
        assert "MODE_CT" in result.columns
        assert result["MODE_CT"].iloc[0] == 10.0

    def test_single_value_session(self) -> None:
        """Session with one shot returns that CT as mode."""
        df = _make_session_df([7.5])
        result = calculate_mode_ct(df)
        assert result["MODE_CT"].iloc[0] == 7.5

    def test_rounding_at_mode_ct_decimals(self) -> None:
        """CT values are rounded to 2 decimals before mode calculation."""
        # 10.004 and 10.005 round to 10.0 and 10.01 respectively
        df = _make_session_df([10.004, 10.004, 10.005, 10.005, 10.005])
        result = calculate_mode_ct(df)
        # 10.005 rounds to 10.01 (3 occurrences) vs 10.004 rounds to 10.0 (2)
        assert result["MODE_CT"].iloc[0] == 10.01

    def test_bimodal_tie_break(self) -> None:
        """When two values tie, scipy.stats.mode returns the smaller value."""
        df = _make_session_df([10.0, 10.0, 12.0, 12.0])
        result = calculate_mode_ct(df)
        # scipy mode with keepdims returns smallest when tied
        assert result["MODE_CT"].iloc[0] == 10.0

    def test_preserves_existing_columns(self) -> None:
        """Original columns remain after mode calculation."""
        df = _make_session_df([10.0, 10.0, 10.0])
        df["EXTRA_COL"] = "test"
        result = calculate_mode_ct(df)
        assert "EXTRA_COL" in result.columns


# ===================================================================
# detect_stops
# ===================================================================


class TestDetectStops:
    """Tests for detect_stops."""

    def test_hard_stop(self) -> None:
        """CT >= 999.9 is flagged as a stop."""
        df = _make_session_df([10.0, 10.0, 999.9])
        df = calculate_mode_ct(df)
        result = detect_stops(df)
        # Last shot (CT=999.9) should be flagged, but check non-first shots
        assert result.iloc[2]["STOP"] == 1

    def test_mode_band_violation(self) -> None:
        """CT deviating >5% from mode triggers stop."""
        # Mode = 10.0, so 10.51 is >5% deviation
        df = _make_session_df([10.0, 10.0, 10.0, 10.51])
        df = calculate_mode_ct(df)
        result = detect_stops(df)
        assert result.iloc[3]["STOP"] == 1

    def test_gap_violation(self) -> None:
        """Time gap > CT + 2s triggers stop."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 3,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [
                        base,
                        base + timedelta(seconds=10),
                        # Gap of 20s with CT=10.0 -> 20 > 10+2 = stop
                        base + timedelta(seconds=30),
                    ]
                ),
                "CT": [10.0, 10.0, 10.0],
                "SESSION_ID": [1, 1, 1],
                "MODE_CT": [10.0, 10.0, 10.0],
            }
        )
        df["SHOT_DIFF_SEC"] = df["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
        df.loc[df.index[0], "SHOT_DIFF_SEC"] = None
        # Second shot: gap 10s, CT 10 + 2 = 12, 10 < 12 => no stop
        # Third shot: gap 20s, CT 10 + 2 = 12, 20 > 12 => stop
        result = detect_stops(df)
        assert result.iloc[1]["STOP"] == 0
        assert result.iloc[2]["STOP"] == 1

    def test_first_shot_always_zero(self) -> None:
        """First shot of each session is always STOP = 0 regardless of CT."""
        df = _make_session_df([999.9, 10.0, 10.0])
        df = calculate_mode_ct(df)
        result = detect_stops(df)
        # First shot has NaN SHOT_DIFF_SEC so it is always 0
        assert result.iloc[0]["STOP"] == 0

    def test_all_normal_no_stops(self) -> None:
        """Normal cadence within mode band produces no stops (except possibly first)."""
        df = _make_session_df([10.0, 10.0, 10.0, 10.0, 10.0])
        df = calculate_mode_ct(df)
        result = detect_stops(df)
        assert result["STOP"].sum() == 0

    def test_combined_criteria(self) -> None:
        """Multiple criteria can overlap, but stop is still binary 0 or 1."""
        # Shot with CT=999.9 AND huge gap
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 3,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [
                        base,
                        base + timedelta(seconds=10),
                        base + timedelta(seconds=100),
                    ]
                ),
                "CT": [10.0, 10.0, 999.9],
                "SESSION_ID": [1, 1, 1],
                "MODE_CT": [10.0, 10.0, 10.0],
            }
        )
        df["SHOT_DIFF_SEC"] = df["LOCAL_SHOT_TIME"].diff().dt.total_seconds()
        df.loc[df.index[0], "SHOT_DIFF_SEC"] = None
        result = detect_stops(df)
        # Should be flagged but value is still 1, not 2 or 3
        assert result.iloc[2]["STOP"] == 1

    def test_output_dtype_is_int(self) -> None:
        """STOP column is integer dtype."""
        df = _make_session_df([10.0, 10.0, 10.0])
        df = calculate_mode_ct(df)
        result = detect_stops(df)
        assert result["STOP"].dtype in (np.int64, np.int32, int)


# ===================================================================
# calculate_run_efficiency
# ===================================================================


class TestCalculateRunEfficiency:
    """Tests for calculate_run_efficiency."""

    def test_basic(self, sessioned_df: pd.DataFrame) -> None:
        """RUN_EFFICIENCY and TOTAL_RUN_TIME columns are added."""
        df = calculate_mode_ct(sessioned_df)
        df = detect_stops(df)
        result = calculate_run_efficiency(df)
        assert "RUN_EFFICIENCY" in result.columns
        assert "TOTAL_RUN_TIME" in result.columns

    def test_all_productive_100_percent(self) -> None:
        """If all shots are productive (STOP=0), efficiency approaches 100%."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        n = 10
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * n,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [base + timedelta(seconds=i * 10) for i in range(n)]
                ),
                "CT": [10.0] * n,
                "SESSION_ID": [1] * n,
                "MODE_CT": [10.0] * n,
                "STOP": [0] * n,
            }
        )
        result = calculate_run_efficiency(df)
        eff = result["RUN_EFFICIENCY"].iloc[0]
        assert eff == 100.0

    def test_all_stops_zero_percent(self) -> None:
        """If all non-first shots are stops, efficiency is 0% (first is forced 0)."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 4,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [
                        base,
                        base + timedelta(seconds=10),
                        base + timedelta(seconds=20),
                        base + timedelta(seconds=30),
                    ]
                ),
                "CT": [10.0, 10.0, 10.0, 10.0],
                "SESSION_ID": [1, 1, 1, 1],
                "MODE_CT": [10.0, 10.0, 10.0, 10.0],
                "STOP": [1, 1, 1, 1],
            }
        )
        result = calculate_run_efficiency(df)
        eff = result["RUN_EFFICIENCY"].iloc[0]
        assert eff == 0.0

    def test_clamped_0_to_100(self) -> None:
        """Efficiency is clamped between 0 and 100."""
        df = _make_session_df([10.0, 10.0, 10.0, 10.0])
        df = calculate_mode_ct(df)
        df = detect_stops(df)
        result = calculate_run_efficiency(df)
        eff_values = result["RUN_EFFICIENCY"].unique()
        for v in eff_values:
            assert 0 <= v <= 100

    def test_last_ct_over_threshold_uses_mode(self) -> None:
        """When last CT > 999.9, MODE_CT is used for total run time."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 3,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [
                        base,
                        base + timedelta(seconds=10),
                        base + timedelta(seconds=20),
                    ]
                ),
                "CT": [10.0, 10.0, 1000.0],
                "SESSION_ID": [1, 1, 1],
                "MODE_CT": [10.0, 10.0, 10.0],
                "STOP": [0, 0, 1],
            }
        )
        result = calculate_run_efficiency(df)
        # TOTAL_RUN_TIME = (20-0) + 10.0 (MODE_CT) = 30.0
        assert result["TOTAL_RUN_TIME"].iloc[0] == 30.0

    def test_single_shot_session(self) -> None:
        """Single shot session has TOTAL_RUN_TIME = CT (time_span=0)."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"],
                "LOCAL_SHOT_TIME": pd.to_datetime([base]),
                "CT": [10.0],
                "SESSION_ID": [1],
                "MODE_CT": [10.0],
                "STOP": [0],
            }
        )
        result = calculate_run_efficiency(df)
        assert result["TOTAL_RUN_TIME"].iloc[0] == 10.0
        assert result["RUN_EFFICIENCY"].iloc[0] == 100.0


# ===================================================================
# calculate_weighted_efficiency
# ===================================================================


class TestCalculateWeightedEfficiency:
    """Tests for calculate_weighted_efficiency."""

    def test_basic_weighted_avg(self, calculated_df: pd.DataFrame) -> None:
        """Weighted average is a float between 0 and 100."""
        result = calculate_weighted_efficiency(calculated_df)
        assert 0 <= result <= 100

    def test_equal_weights(self) -> None:
        """Sessions with equal shot counts yield arithmetic mean."""
        df = pd.DataFrame(
            {
                "SESSION_ID": [1, 1, 2, 2],
                "RUN_EFFICIENCY": [80.0, 80.0, 60.0, 60.0],
            }
        )
        result = calculate_weighted_efficiency(df)
        # Equal weights: (80+60)/2 = 70
        assert result == 70.0

    def test_session_ids_filter(self) -> None:
        """Only specified session_ids are included."""
        df = pd.DataFrame(
            {
                "SESSION_ID": [1, 1, 2, 2, 3, 3],
                "RUN_EFFICIENCY": [80.0, 80.0, 60.0, 60.0, 40.0, 40.0],
            }
        )
        result = calculate_weighted_efficiency(df, session_ids=[1, 2])
        assert result == 70.0

    def test_empty_filter_returns_zero(self) -> None:
        """Filtering to nonexistent sessions returns 0."""
        df = pd.DataFrame(
            {
                "SESSION_ID": [1, 2],
                "RUN_EFFICIENCY": [80.0, 60.0],
            }
        )
        result = calculate_weighted_efficiency(df, session_ids=[999])
        assert result == 0


# ===================================================================
# _calculate_mttr / _calculate_mtbf
# ===================================================================


class TestMttrMtbf:
    """Tests for _calculate_mttr and _calculate_mtbf."""

    def test_mttr_basic(self) -> None:
        """MTTR converts seconds to minutes correctly."""
        # 600s downtime / 3 events = 200s = 3.33 minutes
        result = _calculate_mttr(600, 3)
        assert abs(result - 3.3333) < 0.01

    def test_mttr_zero_events(self) -> None:
        """Zero stop events returns 0."""
        assert _calculate_mttr(600, 0) == 0

    def test_mtbf_basic(self) -> None:
        """MTBF converts seconds to minutes correctly."""
        # 1200s production / 4 events = 300s = 5.0 minutes
        result = _calculate_mtbf(1200, 4)
        assert result == 5.0

    def test_mtbf_zero_events(self) -> None:
        """Zero stop events returns 0."""
        assert _calculate_mtbf(1200, 0) == 0


# ===================================================================
# calculate_stop_metrics
# ===================================================================


class TestCalculateStopMetrics:
    """Tests for calculate_stop_metrics."""

    def test_basic(self, calculated_df: pd.DataFrame) -> None:
        """Stop metric columns are added."""
        result = calculate_stop_metrics(calculated_df)
        for col in (
            "TOTAL_STOPS",
            "DOWNTIME",
            "PRODUCTION_TIME",
            "STOP_EVENTS",
            "MTTR",
            "MTBF",
        ):
            assert col in result.columns

    def test_consecutive_stops_single_event(self) -> None:
        """Back-to-back stops count as 1 stop event."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 5,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [base + timedelta(seconds=i * 10) for i in range(5)]
                ),
                "CT": [10.0] * 5,
                "SESSION_ID": [1] * 5,
                "STOP": [0, 1, 1, 1, 0],
            }
        )
        result = calculate_stop_metrics(df)
        assert result["STOP_EVENTS"].iloc[0] == 1
        assert result["TOTAL_STOPS"].iloc[0] == 3

    def test_alternating_stops_multiple_events(self) -> None:
        """Alternating stop/run produces multiple stop events."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 5,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [base + timedelta(seconds=i * 10) for i in range(5)]
                ),
                "CT": [10.0] * 5,
                "SESSION_ID": [1] * 5,
                "STOP": [0, 1, 0, 1, 0],
            }
        )
        result = calculate_stop_metrics(df)
        assert result["STOP_EVENTS"].iloc[0] == 2

    def test_no_stops(self) -> None:
        """Session with no stops has zero for all stop metrics."""
        base = datetime(2025, 6, 1, 8, 0, 0)
        df = pd.DataFrame(
            {
                "EQUIPMENT_CODE": ["EQ_A"] * 3,
                "LOCAL_SHOT_TIME": pd.to_datetime(
                    [base + timedelta(seconds=i * 10) for i in range(3)]
                ),
                "CT": [10.0] * 3,
                "SESSION_ID": [1] * 3,
                "STOP": [0, 0, 0],
            }
        )
        result = calculate_stop_metrics(df)
        assert result["TOTAL_STOPS"].iloc[0] == 0
        assert result["STOP_EVENTS"].iloc[0] == 0
        assert result["DOWNTIME"].iloc[0] == 0.0
        assert result["MTTR"].iloc[0] == 0
        assert result["MTBF"].iloc[0] == 0


# ===================================================================
# validate_calculations
# ===================================================================


class TestValidateCalculations:
    """Tests for validate_calculations."""

    def test_valid(self, calculated_df: pd.DataFrame) -> None:
        """Properly calculated data passes validation."""
        assert validate_calculations(calculated_df) is True

    def test_nan_mode_ct_raises(self, calculated_df: pd.DataFrame) -> None:
        """Raises ValueError when MODE_CT has NaN."""
        df = calculated_df.copy()
        df.loc[df.index[0], "MODE_CT"] = np.nan
        with pytest.raises(ValueError, match="missing MODE_CT"):
            validate_calculations(df)

    def test_invalid_stop_raises(self, calculated_df: pd.DataFrame) -> None:
        """Raises ValueError when STOP has non-binary values."""
        df = calculated_df.copy()
        df.loc[df.index[0], "STOP"] = 2
        with pytest.raises(ValueError, match="non-binary"):
            validate_calculations(df)

    def test_efficiency_out_of_range_raises(self, calculated_df: pd.DataFrame) -> None:
        """Raises ValueError when RUN_EFFICIENCY exceeds 100."""
        df = calculated_df.copy()
        df.loc[df.index[0], "RUN_EFFICIENCY"] = 105.0
        with pytest.raises(ValueError, match="outside.*0.*100"):
            validate_calculations(df)

    def test_negative_total_run_time_raises(self, calculated_df: pd.DataFrame) -> None:
        """Raises ValueError when TOTAL_RUN_TIME is negative."""
        df = calculated_df.copy()
        df["TOTAL_RUN_TIME"] = -1.0
        with pytest.raises(ValueError, match="non-positive"):
            validate_calculations(df)
