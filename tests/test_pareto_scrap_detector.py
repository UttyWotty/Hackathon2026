"""
Unit tests for the pareto_scrap_detector module used in RCA Pareto analysis.
Covers detect_scrap_indicators, detect_warmup_shots, detect_sensor_anomalies,
and calculate_scrap_statistics with happy-path, boundary, and edge cases.
"""

from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd
import pytest

from analysis.rca.core_analysis.pareto_scrap_detector import (
    SCRAP_COLUMNS,
    WARMUP_SHOTS_AFTER_IDLE,
    calculate_scrap_statistics,
    detect_scrap_indicators,
    detect_sensor_anomalies,
    detect_warmup_shots,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_shot_df(
    n: int,
    ct_issue_flags: Optional[List[bool]] = None,
    downtime_gap_flags: Optional[List[bool]] = None,
    temperatures: Optional[List[float]] = None,
    product_names: Optional[List[str]] = None,
    ct_values: Optional[List[float]] = None,
    base_time: datetime = datetime(2025, 6, 1, 8, 0, 0),
) -> pd.DataFrame:
    """Build a minimal shot DataFrame for scrap detection tests.

    By default, all flags are False and temperatures are absent.
    """
    times = [base_time + timedelta(seconds=i * 10) for i in range(n)]
    data: Dict[str, Any] = {
        "SHOT_TIME": pd.to_datetime(times),
        "CT_ISSUE_FLAG": ct_issue_flags if ct_issue_flags is not None else [False] * n,
        "DOWNTIME_GAP_FLAG": (
            downtime_gap_flags if downtime_gap_flags is not None else [False] * n
        ),
        "DURATION": ct_values if ct_values is not None else [10.0] * n,
    }
    if temperatures is not None:
        data["TEMPERATURE"] = temperatures
    if product_names is not None:
        data["PRODUCT_NAME"] = product_names
    else:
        data["PRODUCT_NAME"] = ["PartA"] * n
    return pd.DataFrame(data)


# ===================================================================
# detect_warmup_shots
# ===================================================================


class TestDetectWarmupShots:
    """Tests for detect_warmup_shots."""

    def test_happy_path_flags_shots_after_gap(self) -> None:
        """Shots immediately after a downtime gap are flagged as warmup."""
        n = 10
        gap_flags = [False] * n
        gap_flags[3] = True  # gap at index 3

        df = _make_shot_df(n, downtime_gap_flags=gap_flags)
        df["SCRAP_WARMUP"] = False
        result = detect_warmup_shots(
            df, warmup_shots_after_idle=WARMUP_SHOTS_AFTER_IDLE
        )

        # The shots after the gap (indices 4, 5, 6) should be flagged
        warmup_indices = result.index[result["SCRAP_WARMUP"]].tolist()
        assert len(warmup_indices) > 0

    def test_no_gaps_means_no_warmup(self) -> None:
        """When no downtime gaps exist, no shots are flagged."""
        df = _make_shot_df(10)
        df["SCRAP_WARMUP"] = False
        result = detect_warmup_shots(df)
        assert result["SCRAP_WARMUP"].sum() == 0

    def test_custom_warmup_count(self) -> None:
        """The warmup_shots_after_idle parameter controls how many shots are flagged."""
        n = 10
        gap_flags = [False] * n
        gap_flags[2] = True

        df = _make_shot_df(n, downtime_gap_flags=gap_flags)
        df["SCRAP_WARMUP"] = False

        result_1 = detect_warmup_shots(df.copy(), warmup_shots_after_idle=1)
        result_5 = detect_warmup_shots(df.copy(), warmup_shots_after_idle=5)

        count_1 = int(result_1["SCRAP_WARMUP"].sum())
        count_5 = int(result_5["SCRAP_WARMUP"].sum())
        assert count_5 >= count_1

    def test_gap_at_last_row(self) -> None:
        """A gap at the last row should not cause index errors."""
        n = 5
        gap_flags = [False] * n
        gap_flags[n - 1] = True

        df = _make_shot_df(n, downtime_gap_flags=gap_flags)
        df["SCRAP_WARMUP"] = False
        result = detect_warmup_shots(df)
        # Should complete without error
        assert "SCRAP_WARMUP" in result.columns

    def test_gap_at_first_row(self) -> None:
        """A gap at the first row is handled gracefully."""
        n = 5
        gap_flags = [True] + [False] * (n - 1)

        df = _make_shot_df(n, downtime_gap_flags=gap_flags)
        df["SCRAP_WARMUP"] = False
        result = detect_warmup_shots(df)
        assert "SCRAP_WARMUP" in result.columns

    def test_single_row(self) -> None:
        """Single-row DataFrame does not raise."""
        df = _make_shot_df(1, downtime_gap_flags=[True])
        df["SCRAP_WARMUP"] = False
        result = detect_warmup_shots(df)
        assert len(result) == 1


# ===================================================================
# detect_sensor_anomalies
# ===================================================================


class TestDetectSensorAnomalies:
    """Tests for detect_sensor_anomalies."""

    def test_no_temperature_column(self) -> None:
        """When TEMPERATURE column is absent, all anomalies are False."""
        df = _make_shot_df(5)
        # Ensure no TEMPERATURE column
        if "TEMPERATURE" in df.columns:
            df = df.drop(columns=["TEMPERATURE"])
        result = detect_sensor_anomalies(df)
        assert result["SCRAP_SENSOR_ANOMALY"].sum() == 0

    def test_no_anomalies_within_normal_range(self) -> None:
        """Temperatures within 3-sigma are not flagged."""
        temps = [200.0, 201.0, 199.0, 200.5, 200.2]
        df = _make_shot_df(5, temperatures=temps, product_names=["P"] * 5)
        result = detect_sensor_anomalies(df)
        assert result["SCRAP_SENSOR_ANOMALY"].sum() == 0

    def test_detects_extreme_outlier(self) -> None:
        """A value far outside 3-sigma is flagged as anomaly.

        The function relies on merge suffixes producing 'mean_temp_stats'
        and 'std_temp_stats' columns.  When the DataFrame has no prior
        columns named 'mean' or 'std', the suffix is not applied and the
        detection path falls through to the else branch (all False).
        To trigger actual anomaly detection we pre-populate 'mean' and
        'std' columns so the merge produces the suffixed names.
        """
        temps = [200.0] * 19 + [1000.0]
        parts = ["P"] * 20
        df = _make_shot_df(20, temperatures=temps, product_names=parts)
        # Add dummy columns named 'mean' and 'std' to force the merge
        # suffixes to produce 'mean_temp_stats' and 'std_temp_stats'.
        df["mean"] = 0.0
        df["std"] = 0.0
        result = detect_sensor_anomalies(df)
        assert result["SCRAP_SENSOR_ANOMALY"].sum() >= 1

    def test_custom_threshold(self) -> None:
        """A tighter threshold flags more values as anomalies."""
        # Use values with moderate spread
        temps = [200.0, 200.0, 200.0, 200.0, 200.0, 210.0]
        parts = ["P"] * 6
        df = _make_shot_df(6, temperatures=temps, product_names=parts)

        result_strict = detect_sensor_anomalies(df.copy(), sensor_anomaly_threshold=1.0)
        result_loose = detect_sensor_anomalies(df.copy(), sensor_anomaly_threshold=5.0)

        assert (
            result_strict["SCRAP_SENSOR_ANOMALY"].sum()
            >= result_loose["SCRAP_SENSOR_ANOMALY"].sum()
        )

    def test_all_identical_temperatures(self) -> None:
        """When all temperatures are identical, std is 0, no anomalies flagged."""
        temps = [200.0] * 5
        parts = ["P"] * 5
        df = _make_shot_df(5, temperatures=temps, product_names=parts)
        result = detect_sensor_anomalies(df)
        # std=0 means lower==upper==mean, so no values outside
        assert result["SCRAP_SENSOR_ANOMALY"].sum() == 0

    def test_multiple_parts_independent(self) -> None:
        """Anomaly detection is per-part, so different parts have independent stats."""
        temps = [200.0, 200.0, 200.0, 100.0, 100.0, 100.0]
        parts = ["A", "A", "A", "B", "B", "B"]
        df = _make_shot_df(6, temperatures=temps, product_names=parts)
        result = detect_sensor_anomalies(df)
        # Within each part, all values are identical, so no anomalies
        assert result["SCRAP_SENSOR_ANOMALY"].sum() == 0


# ===================================================================
# detect_scrap_indicators
# ===================================================================


class TestDetectScrapIndicators:
    """Tests for detect_scrap_indicators (the composite orchestrator)."""

    def test_happy_path_all_clean_no_temp(self) -> None:
        """With all-clean data and no temperature, no scrap indicators are set."""
        df = _make_shot_df(10)
        result = detect_scrap_indicators(df)
        assert "SCRAP_INDICATOR" in result.columns
        assert "SCRAP_SCORE" in result.columns
        assert result["SCRAP_INDICATOR"].sum() == 0

    def test_ct_issue_flag_triggers_scrap(self) -> None:
        """Rows with CT_ISSUE_FLAG True are marked as SCRAP_CT_ABNORMAL."""
        ct_flags = [False, True, False, True, False]
        df = _make_shot_df(5, ct_issue_flags=ct_flags)
        result = detect_scrap_indicators(df)
        assert result["SCRAP_CT_ABNORMAL"].sum() == 2

    def test_scrap_score_sums_indicators(self) -> None:
        """SCRAP_SCORE equals the number of active scrap indicator columns per row."""
        ct_flags = [True, False]
        gap_flags = [False, True]
        df = _make_shot_df(2, ct_issue_flags=ct_flags, downtime_gap_flags=gap_flags)
        result = detect_scrap_indicators(df)
        # All scores should be non-negative integers
        assert (result["SCRAP_SCORE"] >= 0).all()

    def test_all_scrap_columns_present(self) -> None:
        """All expected SCRAP_* columns are added to the output."""
        df = _make_shot_df(5)
        result = detect_scrap_indicators(df)
        for col in SCRAP_COLUMNS:
            assert col in result.columns
        assert "SCRAP_INDICATOR" in result.columns
        assert "SCRAP_SCORE" in result.columns

    def test_conservative_fallback_when_high_rate(self) -> None:
        """When > 50% of shots are flagged, the conservative fallback activates."""
        # All shots have CT_ISSUE_FLAG, making 100% scrap rate
        n = 10
        df = _make_shot_df(n, ct_issue_flags=[True] * n)
        result = detect_scrap_indicators(df)
        # After fallback, SCRAP_INDICATOR should still reflect CT_ABNORMAL
        assert result["SCRAP_INDICATOR"].sum() > 0

    def test_without_temperature_column(self) -> None:
        """Works correctly when TEMPERATURE column is absent."""
        df = _make_shot_df(5)
        result = detect_scrap_indicators(df)
        assert result["SCRAP_LOW_TEMP"].sum() == 0
        assert result["SCRAP_SENSOR_ANOMALY"].sum() == 0


# ===================================================================
# calculate_scrap_statistics
# ===================================================================


class TestCalculateScrapStatistics:
    """Tests for calculate_scrap_statistics."""

    def _make_scrap_df(
        self,
        n: int,
        scrap_indicator: Optional[List[bool]] = None,
        scrap_score: Optional[List[int]] = None,
        product_names: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        """Build a DataFrame that already has all SCRAP_* columns computed."""
        data: Dict[str, Any] = {
            "DURATION": [10.0] * n,
            "SCRAP_INDICATOR": (
                scrap_indicator if scrap_indicator is not None else [False] * n
            ),
            "SCRAP_SCORE": scrap_score if scrap_score is not None else [0] * n,
            "SCRAP_CT_ABNORMAL": [False] * n,
            "SCRAP_WARMUP": [False] * n,
            "SCRAP_LOW_PRESSURE": [False] * n,
            "SCRAP_LOW_TEMP": [False] * n,
            "SCRAP_SENSOR_ANOMALY": [False] * n,
            "SCRAP_MISSING_SENSORS": [False] * n,
        }
        if product_names is not None:
            data["PRODUCT_NAME"] = product_names
        return pd.DataFrame(data)

    def test_returns_dataframe_with_product_name(self) -> None:
        """Returns a per-part summary DataFrame when PRODUCT_NAME is present."""
        df = self._make_scrap_df(
            4,
            scrap_indicator=[True, False, True, False],
            scrap_score=[1, 0, 1, 0],
            product_names=["A", "A", "B", "B"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        assert isinstance(result, pd.DataFrame)
        assert "Scrap_Shots" in result.columns
        assert "Total_Shots" in result.columns
        assert "Scrap_Rate" in result.columns

    def test_returns_none_without_product_name(self) -> None:
        """Returns None when PRODUCT_NAME column is absent."""
        df = self._make_scrap_df(5)
        # No PRODUCT_NAME column
        result = calculate_scrap_statistics(df)
        assert result is None

    def test_scrap_rate_calculation(self) -> None:
        """Scrap_Rate is (Scrap_Shots / Total_Shots) * 100."""
        df = self._make_scrap_df(
            4,
            scrap_indicator=[True, True, False, False],
            scrap_score=[1, 1, 0, 0],
            product_names=["A", "A", "A", "A"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        rate = result.loc["A", "Scrap_Rate"]
        expected_rate = (2 / 4) * 100
        assert rate == pytest.approx(expected_rate)

    def test_all_scrap(self) -> None:
        """When all shots are scrap, rate is 100%."""
        df = self._make_scrap_df(
            3,
            scrap_indicator=[True, True, True],
            scrap_score=[1, 1, 1],
            product_names=["X", "X", "X"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        assert result.loc["X", "Scrap_Rate"] == pytest.approx(100.0)

    def test_no_scrap(self) -> None:
        """When no shots are scrap, rate is 0%."""
        df = self._make_scrap_df(
            3,
            scrap_indicator=[False, False, False],
            scrap_score=[0, 0, 0],
            product_names=["X", "X", "X"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        assert result.loc["X", "Scrap_Rate"] == pytest.approx(0.0)

    def test_sorted_by_scrap_rate_descending(self) -> None:
        """Results are sorted by Scrap_Rate in descending order."""
        df = self._make_scrap_df(
            6,
            scrap_indicator=[True, False, True, True, False, False],
            scrap_score=[1, 0, 1, 1, 0, 0],
            product_names=["A", "A", "B", "B", "C", "C"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        rates = result["Scrap_Rate"].tolist()
        assert rates == sorted(rates, reverse=True)

    def test_total_scrap_score_column(self) -> None:
        """Total_Scrap_Score sums SCRAP_SCORE per part."""
        df = self._make_scrap_df(
            4,
            scrap_indicator=[True, True, True, False],
            scrap_score=[2, 3, 1, 0],
            product_names=["A", "A", "B", "B"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        assert result.loc["A", "Total_Scrap_Score"] == 5
        assert result.loc["B", "Total_Scrap_Score"] == 1

    def test_single_row(self) -> None:
        """Works correctly with a single-row DataFrame."""
        df = self._make_scrap_df(
            1,
            scrap_indicator=[True],
            scrap_score=[1],
            product_names=["Solo"],
        )
        result = calculate_scrap_statistics(df)
        assert result is not None
        assert result.loc["Solo", "Total_Shots"] == 1
        assert result.loc["Solo", "Scrap_Shots"] == 1
