"""
Unit tests for the pareto_deviations module.
Covers calculate_std_deviations, calculate_iqr_deviations, combine_deviation_methods,
and calculate_statistical_deviations with happy-path, boundary, and error cases.
All tests use in-memory DataFrames with no I/O.
"""

from datetime import datetime, timedelta
from typing import List

import numpy as np
import pandas as pd

from analysis.rca.core_analysis.pareto_deviations import (
    CRITICAL_DEVIATION_PCT,
    HIGH_DEVIATION_PCT,
    MIN_GROUP_SIZE,
    MODERATE_DEVIATION_PCT,
    OUTLIER_METHODS_REQUIRED,
    SIGNIFICANT_DEVIATION_PCT,
    calculate_iqr_deviations,
    calculate_statistical_deviations,
    calculate_std_deviations,
    combine_deviation_methods,
)

# ===================================================================
# Helpers
# ===================================================================


def _make_shot_df(
    ct_values: List[float],
    equipment: str = "EQ_A",
    part: str = "PART_1",
    base_time: datetime = datetime(2025, 6, 1, 8, 0, 0),
) -> pd.DataFrame:
    """Build a minimal shot DataFrame from a list of CT values."""
    n = len(ct_values)
    times = [base_time + timedelta(seconds=i * 10) for i in range(n)]
    return pd.DataFrame(
        {
            "MACHINE_ID": [equipment] * n,
            "PRODUCT_NAME": [part] * n,
            "DURATION": ct_values,
            "SHOT_TIME": pd.to_datetime(times),
        }
    )


def _make_large_group(
    n: int = 20,
    base_ct: float = 10.0,
    std: float = 0.5,
    equipment: str = "EQ_A",
    part: str = "PART_1",
) -> pd.DataFrame:
    """Build a DataFrame with n rows of normally distributed CT values."""
    rng = np.random.RandomState(42)
    ct_values = rng.normal(base_ct, std, n).tolist()
    return _make_shot_df(ct_values, equipment=equipment, part=part)


# ===================================================================
# calculate_std_deviations
# ===================================================================


class TestCalculateStdDeviations:
    """Tests for calculate_std_deviations."""

    def test_happy_path_adds_columns(self) -> None:
        """Standard deviation method adds STD_OUTLIER and deviation columns."""
        df = _make_large_group(n=15)
        result = calculate_std_deviations(df)
        assert "STD_OUTLIER" in result.columns
        assert "DEVIATION_FROM_MEAN_PCT" in result.columns

    def test_outlier_detected_for_extreme_value(self) -> None:
        """A CT value far from the mean is flagged as an STD outlier."""
        ct_values = [10.0] * 14 + [50.0]
        df = _make_shot_df(ct_values)
        result = calculate_std_deviations(df)
        outlier_row = result[result["DURATION"] == 50.0]
        assert bool(outlier_row["STD_OUTLIER"].iloc[0]) is True

    def test_no_outliers_in_tight_group(self) -> None:
        """All values within N-sigma are not flagged."""
        ct_values = [10.0] * 15
        df = _make_shot_df(ct_values)
        result = calculate_std_deviations(df)
        assert result["STD_OUTLIER"].sum() == 0

    def test_group_below_min_size_gets_nan(self) -> None:
        """Groups with fewer than MIN_GROUP_SIZE rows get NaN deviation."""
        df = _make_shot_df([10.0] * (MIN_GROUP_SIZE - 1))
        result = calculate_std_deviations(df)
        assert result["DEVIATION_FROM_MEAN_PCT"].isna().all()

    def test_custom_threshold(self) -> None:
        """A lower threshold flags more points as outliers."""
        df = _make_large_group(n=20, base_ct=10.0, std=1.0)
        result_strict = calculate_std_deviations(df.copy(), std_threshold=1.0)
        result_loose = calculate_std_deviations(df.copy(), std_threshold=5.0)
        assert result_strict["STD_OUTLIER"].sum() >= result_loose["STD_OUTLIER"].sum()

    def test_deviation_pct_sign(self) -> None:
        """CT above mean yields positive deviation, below yields negative."""
        ct_values = [10.0] * 14 + [15.0]
        df = _make_shot_df(ct_values)
        result = calculate_std_deviations(df)
        above_mean_row = result[result["DURATION"] == 15.0]
        assert above_mean_row["DEVIATION_FROM_MEAN_PCT"].iloc[0] > 0

    def test_preserves_existing_columns(self) -> None:
        """Original columns are preserved after calculation."""
        df = _make_large_group(n=12)
        df["EXTRA"] = "keep_me"
        result = calculate_std_deviations(df)
        assert "EXTRA" in result.columns


# ===================================================================
# calculate_iqr_deviations
# ===================================================================


class TestCalculateIqrDeviations:
    """Tests for calculate_iqr_deviations."""

    def test_happy_path_adds_columns(self) -> None:
        """IQR method adds IQR_OUTLIER and deviation columns."""
        df = _make_large_group(n=15)
        result = calculate_iqr_deviations(df)
        assert "IQR_OUTLIER" in result.columns
        assert "DEVIATION_FROM_MEDIAN_PCT" in result.columns

    def test_outlier_detected_for_extreme_value(self) -> None:
        """A CT value far beyond Q3 + 1.5*IQR is flagged."""
        ct_values = [10.0] * 14 + [100.0]
        df = _make_shot_df(ct_values)
        result = calculate_iqr_deviations(df)
        outlier_row = result[result["DURATION"] == 100.0]
        assert bool(outlier_row["IQR_OUTLIER"].iloc[0]) is True

    def test_no_outliers_in_uniform_group(self) -> None:
        """Identical CT values produce zero IQR and no outliers."""
        ct_values = [10.0] * 15
        df = _make_shot_df(ct_values)
        result = calculate_iqr_deviations(df)
        assert result["IQR_OUTLIER"].sum() == 0

    def test_group_below_min_size_gets_nan(self) -> None:
        """Groups smaller than MIN_GROUP_SIZE get NaN median deviation."""
        df = _make_shot_df([10.0] * (MIN_GROUP_SIZE - 1))
        result = calculate_iqr_deviations(df)
        assert result["DEVIATION_FROM_MEDIAN_PCT"].isna().all()

    def test_custom_multiplier(self) -> None:
        """A smaller IQR multiplier flags more outliers."""
        df = _make_large_group(n=20, base_ct=10.0, std=2.0)
        result_strict = calculate_iqr_deviations(df.copy(), iqr_multiplier=0.5)
        result_loose = calculate_iqr_deviations(df.copy(), iqr_multiplier=5.0)
        assert result_strict["IQR_OUTLIER"].sum() >= result_loose["IQR_OUTLIER"].sum()

    def test_median_deviation_sign(self) -> None:
        """CT below median yields negative deviation percentage."""
        ct_values = [10.0] * 10 + [20.0] * 5
        df = _make_shot_df(ct_values)
        result = calculate_iqr_deviations(df)
        median_val = df["DURATION"].median()
        below_median = result[result["DURATION"] < median_val]
        if len(below_median) > 0:
            assert (below_median["DEVIATION_FROM_MEDIAN_PCT"].dropna() < 0).all()


# ===================================================================
# combine_deviation_methods
# ===================================================================


class TestCombineDeviationMethods:
    """Tests for combine_deviation_methods."""

    def test_happy_path_adds_composite_columns(self) -> None:
        """Combine adds OUTLIER_SCORE, DEVIATION_PCT, DURATION_ISSUE_FLAG, DURATION_ISSUE_TYPE."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0, 20.0, 30.0],
                "STD_OUTLIER": [False, True, True],
                "IQR_OUTLIER": [False, True, True],
                "ZSCORE_OUTLIER": [False, False, True],
                "PERCENTILE_OUTLIER": [False, False, True],
                "ROLLING_OUTLIER": [False, False, True],
                "DEVIATION_FROM_MEAN_PCT": [1.0, 10.0, 60.0],
                "DEVIATION_FROM_MEDIAN_PCT": [1.0, 10.0, 55.0],
                "DEVIATION_PERCENTILE": [1.0, 10.0, 65.0],
            }
        )
        result = combine_deviation_methods(df)
        assert "OUTLIER_SCORE" in result.columns
        assert "DEVIATION_PCT" in result.columns
        assert "CT_ISSUE_FLAG" in result.columns
        assert "CT_ISSUE_TYPE" in result.columns

    def test_outlier_score_sums_flags(self) -> None:
        """OUTLIER_SCORE is the sum of all five outlier boolean columns."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [True],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [5.0],
                "DEVIATION_FROM_MEDIAN_PCT": [5.0],
                "DEVIATION_PERCENTILE": [5.0],
            }
        )
        result = combine_deviation_methods(df)
        assert result["OUTLIER_SCORE"].iloc[0] == 3

    def test_issue_flag_by_outlier_count(self) -> None:
        """CT_ISSUE_FLAG is True when OUTLIER_SCORE >= OUTLIER_METHODS_REQUIRED."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [5.0],
                "DEVIATION_FROM_MEDIAN_PCT": [5.0],
                "DEVIATION_PERCENTILE": [5.0],
            }
        )
        result = combine_deviation_methods(df)
        assert result["OUTLIER_SCORE"].iloc[0] == OUTLIER_METHODS_REQUIRED
        assert bool(result["CT_ISSUE_FLAG"].iloc[0]) is True

    def test_issue_flag_by_high_deviation(self) -> None:
        """CT_ISSUE_FLAG is True when deviation exceeds HIGH_DEVIATION_PCT."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [False],
                "IQR_OUTLIER": [False],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [HIGH_DEVIATION_PCT + 1],
                "DEVIATION_FROM_MEDIAN_PCT": [0.0],
                "DEVIATION_PERCENTILE": [0.0],
            }
        )
        result = combine_deviation_methods(df)
        assert bool(result["CT_ISSUE_FLAG"].iloc[0]) is True

    def test_normal_type_no_issues(self) -> None:
        """CT_ISSUE_TYPE is Normal when no issue flag is set."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [False],
                "IQR_OUTLIER": [False],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [1.0],
                "DEVIATION_FROM_MEDIAN_PCT": [1.0],
                "DEVIATION_PERCENTILE": [1.0],
            }
        )
        result = combine_deviation_methods(df)
        assert result["CT_ISSUE_TYPE"].iloc[0] == "Normal"

    def test_critical_issue_type(self) -> None:
        """CT_ISSUE_TYPE is Critical when deviation > CRITICAL_DEVIATION_PCT."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [True],
                "PERCENTILE_OUTLIER": [True],
                "ROLLING_OUTLIER": [True],
                "DEVIATION_FROM_MEAN_PCT": [CRITICAL_DEVIATION_PCT + 10],
                "DEVIATION_FROM_MEDIAN_PCT": [CRITICAL_DEVIATION_PCT + 10],
                "DEVIATION_PERCENTILE": [CRITICAL_DEVIATION_PCT + 10],
            }
        )
        result = combine_deviation_methods(df)
        assert result["CT_ISSUE_TYPE"].iloc[0] == "Critical"

    def test_significant_issue_type(self) -> None:
        """CT_ISSUE_TYPE is Significant when deviation is between thresholds."""
        deviation = SIGNIFICANT_DEVIATION_PCT + 1
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [deviation],
                "DEVIATION_FROM_MEDIAN_PCT": [deviation],
                "DEVIATION_PERCENTILE": [deviation],
            }
        )
        result = combine_deviation_methods(df)
        assert result["CT_ISSUE_TYPE"].iloc[0] == "Significant"

    def test_moderate_issue_type(self) -> None:
        """CT_ISSUE_TYPE is Moderate when deviation is between moderate and significant."""
        deviation = MODERATE_DEVIATION_PCT + 1
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [deviation],
                "DEVIATION_FROM_MEDIAN_PCT": [deviation],
                "DEVIATION_PERCENTILE": [deviation],
            }
        )
        result = combine_deviation_methods(df)
        assert result["CT_ISSUE_TYPE"].iloc[0] == "Moderate"

    def test_minor_issue_type(self) -> None:
        """CT_ISSUE_TYPE is Minor when flagged but deviation is small."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [2.0],
                "DEVIATION_FROM_MEDIAN_PCT": [2.0],
                "DEVIATION_PERCENTILE": [2.0],
            }
        )
        result = combine_deviation_methods(df)
        assert result["CT_ISSUE_TYPE"].iloc[0] == "Minor"

    def test_missing_outlier_cols_defaults_false(self) -> None:
        """Missing outlier columns are defaulted to False."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "DEVIATION_FROM_MEAN_PCT": [1.0],
                "DEVIATION_FROM_MEDIAN_PCT": [1.0],
                "DEVIATION_PERCENTILE": [1.0],
            }
        )
        result = combine_deviation_methods(df)
        assert result["OUTLIER_SCORE"].iloc[0] == 0

    def test_missing_deviation_cols_defaults_zero(self) -> None:
        """Missing deviation columns are defaulted to 0.0."""
        df = pd.DataFrame(
            {
                "DURATION": [10.0],
                "STD_OUTLIER": [False],
                "IQR_OUTLIER": [False],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
            }
        )
        result = combine_deviation_methods(df)
        assert result["DEVIATION_PCT"].iloc[0] == 0.0

    def test_target_duration_blending(self) -> None:
        """TARGET_DURATION column blends into DEVIATION_PCT."""
        df = pd.DataFrame(
            {
                "DURATION": [20.0],
                "TARGET_DURATION": [10.0],
                "STD_OUTLIER": [True],
                "IQR_OUTLIER": [True],
                "ZSCORE_OUTLIER": [False],
                "PERCENTILE_OUTLIER": [False],
                "ROLLING_OUTLIER": [False],
                "DEVIATION_FROM_MEAN_PCT": [30.0],
                "DEVIATION_FROM_MEDIAN_PCT": [30.0],
                "DEVIATION_PERCENTILE": [30.0],
            }
        )
        result = combine_deviation_methods(df)
        deviation = result["DEVIATION_PCT"].iloc[0]
        approved_dev = abs((20.0 - 10.0) / 10.0 * 100)
        expected = 30.0 * 0.7 + approved_dev * 0.3
        assert abs(deviation - expected) < 0.01


# ===================================================================
# calculate_statistical_deviations (orchestrator)
# ===================================================================


class TestCalculateStatisticalCtDeviations:
    """Tests for the orchestrator calculate_statistical_deviations."""

    def test_happy_path_all_columns_present(self) -> None:
        """Orchestrator produces all expected deviation and composite columns."""
        df = _make_large_group(n=25)
        result = calculate_statistical_deviations(df)
        expected_cols = [
            "STD_OUTLIER",
            "IQR_OUTLIER",
            "ZSCORE_OUTLIER",
            "PERCENTILE_OUTLIER",
            "ROLLING_OUTLIER",
            "OUTLIER_SCORE",
            "DEVIATION_PCT",
            "CT_ISSUE_FLAG",
            "CT_ISSUE_TYPE",
        ]
        for col in expected_cols:
            assert col in result.columns, f"Missing column: {col}"

    def test_row_count_preserved(self) -> None:
        """Number of rows is preserved through the full pipeline."""
        n = 25
        df = _make_large_group(n=n)
        result = calculate_statistical_deviations(df)
        assert len(result) == n

    def test_custom_thresholds_propagate(self) -> None:
        """Custom thresholds flow through to sub-methods."""
        df = _make_large_group(n=25, base_ct=10.0, std=2.0)
        result_strict = calculate_statistical_deviations(
            df.copy(),
            std_threshold=1.0,
            iqr_multiplier=0.5,
            z_score_threshold=0.5,
        )
        result_loose = calculate_statistical_deviations(
            df.copy(),
            std_threshold=5.0,
            iqr_multiplier=5.0,
            z_score_threshold=5.0,
        )
        assert (
            result_strict["CT_ISSUE_FLAG"].sum() >= result_loose["CT_ISSUE_FLAG"].sum()
        )

    def test_multi_equipment_groups(self) -> None:
        """Multiple equipment-part groups are handled independently."""
        df1 = _make_large_group(n=15, equipment="EQ_A", part="PART_1")
        df2 = _make_large_group(n=15, equipment="EQ_B", part="PART_2")
        df = pd.concat([df1, df2], ignore_index=True)
        result = calculate_statistical_deviations(df)
        assert len(result) == 30
        assert set(result["MACHINE_ID"].unique()) == {"EQ_A", "EQ_B"}

    def test_small_group_no_crash(self) -> None:
        """Groups smaller than MIN_GROUP_SIZE do not cause errors."""
        df = _make_shot_df([10.0] * 5)
        result = calculate_statistical_deviations(df)
        assert len(result) == 5
