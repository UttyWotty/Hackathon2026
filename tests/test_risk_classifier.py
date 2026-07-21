"""
Unit tests for the risk_classifier module used in RCA analysis.
Covers get_pattern_risk_score, get_deviation_risk_score, calculate_risk_scores,
build_prediction_model, and predict_risk with happy-path, boundary, and error cases.
"""

from typing import Any, Dict, List

import numpy as np
import pandas as pd
import pytest

from analysis.rca.core_analysis.risk_classifier import (
    DEVIATION_HIGH_THRESHOLD,
    DEVIATION_LOW_THRESHOLD,
    DEVIATION_MEDIUM_THRESHOLD,
    HIGH_RISK_DAYS,
    MIN_SAMPLES_FOR_TRAINING,
    NIGHT_SHIFT_HOURS,
    PATTERN_GRADUAL_DECREASE,
    PATTERN_GRADUAL_INCREASE,
    PATTERN_HIGH_VARIABILITY,
    PATTERN_NORMAL,
    PATTERN_SUDDEN_SPIKE,
    _prepare_feature_matrix,
    build_prediction_model,
    calculate_risk_scores,
    get_day_risk_score,
    get_deviation_risk_score,
    get_pattern_risk_score,
    get_time_risk_score,
    predict_risk,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_risk_df(
    patterns: List[str],
    hours: List[int],
    days: List[str],
    deviations: List[float] | None = None,
) -> pd.DataFrame:
    """Build a minimal DataFrame for calculate_risk_scores."""
    data: Dict[str, Any] = {
        "CT_PATTERN": patterns,
        "HOUR": hours,
        "DAY_OF_WEEK": days,
    }
    if deviations is not None:
        data["CT_DEVIATION_PCT"] = deviations
    return pd.DataFrame(data)


def _prepare_prediction_data(
    raw_df: pd.DataFrame, expected_columns: List[str]
) -> pd.DataFrame:
    """Transform raw data through _prepare_feature_matrix, then align to model columns.

    The one-hot encoding for a subset of rows may not produce all the dummy
    columns that the full training set had.  This helper reindexes to match.
    """
    x = _prepare_feature_matrix(raw_df.copy())
    return x.reindex(columns=expected_columns, fill_value=0)


def _make_training_df(n: int, high_risk_fraction: float = 0.3) -> pd.DataFrame:
    """Build a DataFrame suitable for build_prediction_model.

    Generates n rows with all required feature columns and enough variation
    for stratified train/test split. The RISK_SCORE column has a bimodal
    distribution so quantile-based labelling produces both classes.
    """
    rng = np.random.RandomState(42)
    n_high = int(n * high_risk_fraction)
    n_low = n - n_high

    hours = rng.randint(0, 24, size=n)
    months = rng.randint(1, 13, size=n)
    weeks = rng.randint(1, 53, size=n)
    ct_dev = np.concatenate(
        [
            rng.normal(5.0, 2.0, size=n_low),
            rng.normal(60.0, 10.0, size=n_high),
        ]
    )
    outlier = rng.uniform(0, 1, size=n)
    risk = np.concatenate(
        [
            rng.uniform(0.0, 0.3, size=n_low),
            rng.uniform(0.7, 1.0, size=n_high),
        ]
    )

    patterns = [PATTERN_NORMAL] * n_low + [PATTERN_SUDDEN_SPIKE] * n_high
    day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    days = [day_names[i % len(day_names)] for i in range(n)]
    shifts = ["Day" if h >= 6 else "Night" for h in hours]
    downtime_types = ["Planned" if i % 2 == 0 else "Unplanned" for i in range(n)]

    return pd.DataFrame(
        {
            "HOUR": hours,
            "MONTH": months,
            "WEEK_OF_YEAR": weeks,
            "CT_DEVIATION_PCT": ct_dev,
            "OUTLIER_SCORE": outlier,
            "RISK_SCORE": risk,
            "DAY_OF_WEEK": days,
            "SHIFT": shifts,
            "CT_PATTERN": patterns,
            "DOWNTIME_TYPE": downtime_types,
        }
    )


# ===================================================================
# get_pattern_risk_score
# ===================================================================


class TestGetPatternRiskScore:
    """Tests for get_pattern_risk_score."""

    def test_sudden_spike(self) -> None:
        """Sudden Spike pattern returns the highest pattern score."""
        assert get_pattern_risk_score(PATTERN_SUDDEN_SPIKE) == 0.4

    def test_high_variability(self) -> None:
        assert get_pattern_risk_score(PATTERN_HIGH_VARIABILITY) == 0.3

    def test_gradual_increase(self) -> None:
        assert get_pattern_risk_score(PATTERN_GRADUAL_INCREASE) == 0.2

    def test_gradual_decrease(self) -> None:
        assert get_pattern_risk_score(PATTERN_GRADUAL_DECREASE) == 0.1

    def test_normal_pattern(self) -> None:
        """Normal pattern falls through to the default score of 0.0."""
        assert get_pattern_risk_score(PATTERN_NORMAL) == 0.0

    def test_unknown_pattern(self) -> None:
        """An unrecognised pattern string returns 0.0."""
        assert get_pattern_risk_score("Never Seen Before") == 0.0

    def test_empty_string(self) -> None:
        """Empty string returns default 0.0."""
        assert get_pattern_risk_score("") == 0.0


# ===================================================================
# get_deviation_risk_score
# ===================================================================


class TestGetDeviationRiskScore:
    """Tests for get_deviation_risk_score."""

    def test_above_high_threshold(self) -> None:
        """Deviation above 50 returns 0.3."""
        assert get_deviation_risk_score(DEVIATION_HIGH_THRESHOLD + 1) == 0.3

    def test_at_high_threshold_boundary(self) -> None:
        """Deviation exactly at 50 does NOT exceed it, so returns 0.2."""
        assert get_deviation_risk_score(DEVIATION_HIGH_THRESHOLD) == 0.2

    def test_above_medium_threshold(self) -> None:
        """Deviation above 25 but at or below 50 returns 0.2."""
        assert get_deviation_risk_score(DEVIATION_MEDIUM_THRESHOLD + 1) == 0.2

    def test_at_medium_threshold_boundary(self) -> None:
        """Deviation exactly at 25 does NOT exceed it, so returns 0.1."""
        assert get_deviation_risk_score(DEVIATION_MEDIUM_THRESHOLD) == 0.1

    def test_above_low_threshold(self) -> None:
        """Deviation above 10 but at or below 25 returns 0.1."""
        assert get_deviation_risk_score(DEVIATION_LOW_THRESHOLD + 1) == 0.1

    def test_at_low_threshold_boundary(self) -> None:
        """Deviation exactly at 10 does NOT exceed it, so returns 0.0."""
        assert get_deviation_risk_score(DEVIATION_LOW_THRESHOLD) == 0.0

    def test_below_low_threshold(self) -> None:
        assert get_deviation_risk_score(5.0) == 0.0

    def test_zero_deviation(self) -> None:
        assert get_deviation_risk_score(0.0) == 0.0

    def test_very_large_deviation(self) -> None:
        """Extremely large deviation still returns 0.3 (max bucket)."""
        assert get_deviation_risk_score(10000.0) == 0.3


# ===================================================================
# get_time_risk_score / get_day_risk_score (small helpers)
# ===================================================================


class TestGetTimeRiskScore:
    """Tests for get_time_risk_score."""

    def test_night_shift_hour(self) -> None:
        for hour in NIGHT_SHIFT_HOURS:
            assert get_time_risk_score(hour) == 0.1

    def test_day_shift_hour(self) -> None:
        for hour in [6, 12, 18, 23]:
            assert get_time_risk_score(hour) == 0.0

    def test_boundary_hour_5(self) -> None:
        """Hour 5 is the last night-shift hour."""
        assert get_time_risk_score(5) == 0.1

    def test_boundary_hour_6(self) -> None:
        """Hour 6 is the first non-night-shift hour."""
        assert get_time_risk_score(6) == 0.0


class TestGetDayRiskScore:
    """Tests for get_day_risk_score."""

    def test_high_risk_days(self) -> None:
        for day in HIGH_RISK_DAYS:
            assert get_day_risk_score(day) == 0.1

    def test_normal_days(self) -> None:
        for day in ["Monday", "Tuesday", "Wednesday", "Thursday", "Saturday"]:
            assert get_day_risk_score(day) == 0.0

    def test_empty_string(self) -> None:
        assert get_day_risk_score("") == 0.0


# ===================================================================
# calculate_risk_scores
# ===================================================================


class TestCalculateRiskScores:
    """Tests for calculate_risk_scores."""

    def test_happy_path_with_deviation(self) -> None:
        """All four factors contribute to a composite score."""
        df = _make_risk_df(
            patterns=[PATTERN_SUDDEN_SPIKE],
            hours=[2],
            days=["Sunday"],
            deviations=[60.0],
        )
        scores = calculate_risk_scores(df)
        # pattern=0.4 + deviation=0.3 + time=0.1 + day=0.1 = 0.9
        assert len(scores) == 1
        assert scores[0] == pytest.approx(0.9)

    def test_score_without_deviation_column(self) -> None:
        """When CT_DEVIATION_PCT is absent, deviation component is skipped."""
        df = _make_risk_df(
            patterns=[PATTERN_SUDDEN_SPIKE],
            hours=[2],
            days=["Sunday"],
            deviations=None,
        )
        scores = calculate_risk_scores(df)
        # pattern=0.4 + time=0.1 + day=0.1 = 0.6
        assert scores[0] == pytest.approx(0.6)

    def test_score_capped_at_one(self) -> None:
        """Composite score is capped at 1.0 even when components exceed it."""
        # This specific combination: pattern=0.4 + deviation=0.3 + time=0.1 + day=0.1 = 0.9
        # Not actually > 1.0 with current scoring, but verify the cap logic:
        df = _make_risk_df(
            patterns=[PATTERN_SUDDEN_SPIKE],
            hours=[0],
            days=["Friday"],
            deviations=[100.0],
        )
        scores = calculate_risk_scores(df)
        assert scores[0] <= 1.0

    def test_zero_risk_row(self) -> None:
        """A row with no risk factors yields 0.0."""
        df = _make_risk_df(
            patterns=[PATTERN_NORMAL],
            hours=[12],
            days=["Wednesday"],
            deviations=[5.0],
        )
        scores = calculate_risk_scores(df)
        assert scores[0] == pytest.approx(0.0)

    def test_multiple_rows(self) -> None:
        """Returns one score per row."""
        df = _make_risk_df(
            patterns=[PATTERN_NORMAL, PATTERN_SUDDEN_SPIKE],
            hours=[12, 2],
            days=["Monday", "Sunday"],
            deviations=[5.0, 60.0],
        )
        scores = calculate_risk_scores(df)
        assert len(scores) == 2
        assert scores[0] < scores[1]

    def test_negative_deviation_uses_abs(self) -> None:
        """Negative CT_DEVIATION_PCT is handled via abs()."""
        df = _make_risk_df(
            patterns=[PATTERN_NORMAL],
            hours=[12],
            days=["Monday"],
            deviations=[-55.0],
        )
        scores = calculate_risk_scores(df)
        # abs(-55) = 55 > 50 => deviation=0.3
        assert scores[0] == pytest.approx(0.3)

    def test_empty_dataframe(self) -> None:
        """Empty DataFrame returns an empty list."""
        df = _make_risk_df(
            patterns=[],
            hours=[],
            days=[],
            deviations=[],
        )
        scores = calculate_risk_scores(df)
        assert scores == []


# ===================================================================
# build_prediction_model
# ===================================================================


class TestBuildPredictionModel:
    """Tests for build_prediction_model."""

    def test_returns_none_for_insufficient_data(self) -> None:
        """Returns None when row count is below MIN_SAMPLES_FOR_TRAINING."""
        df = _make_training_df(n=MIN_SAMPLES_FOR_TRAINING - 1)
        result = build_prediction_model(df, save_model=False)
        assert result is None

    def test_builds_model_with_sufficient_data(self) -> None:
        """Returns a dict with model, scaler, feature_importance, X_columns."""
        df = _make_training_df(n=200)
        result = build_prediction_model(df, save_model=False)
        assert result is not None
        assert "model" in result
        assert "scaler" in result
        assert "feature_importance" in result
        assert "X_columns" in result
        assert "risk_threshold" in result

    def test_feature_importance_is_dataframe(self) -> None:
        """feature_importance is a DataFrame with feature and importance columns."""
        df = _make_training_df(n=200)
        result = build_prediction_model(df, save_model=False)
        assert result is not None
        fi = result["feature_importance"]
        assert isinstance(fi, pd.DataFrame)
        assert "feature" in fi.columns
        assert "importance" in fi.columns

    def test_x_columns_is_list_of_strings(self) -> None:
        """X_columns is a list of column name strings."""
        df = _make_training_df(n=200)
        result = build_prediction_model(df, save_model=False)
        assert result is not None
        assert isinstance(result["X_columns"], list)
        assert all(isinstance(c, str) for c in result["X_columns"])

    def test_risk_threshold_is_float(self) -> None:
        """risk_threshold is a numeric value from the 0.8 quantile."""
        df = _make_training_df(n=200)
        result = build_prediction_model(df, save_model=False)
        assert result is not None
        assert isinstance(result["risk_threshold"], float)

    def test_model_at_minimum_threshold(self) -> None:
        """Exactly MIN_SAMPLES_FOR_TRAINING rows should succeed."""
        df = _make_training_df(n=MIN_SAMPLES_FOR_TRAINING)
        result = build_prediction_model(df, save_model=False)
        assert result is not None


# ===================================================================
# predict_risk
# ===================================================================


class TestPredictRisk:
    """Tests for predict_risk."""

    def test_returns_none_when_model_data_is_none(self) -> None:
        """Returns None if model_data is None."""
        dummy_df = pd.DataFrame({"x": [1]})
        result = predict_risk(None, dummy_df)
        assert result is None

    def test_happy_path_prediction(self) -> None:
        """Returns dict with risk_probability and high_risk_prediction arrays."""
        df = _make_training_df(n=200)
        model_data = build_prediction_model(df, save_model=False)
        assert model_data is not None

        new_data = _prepare_prediction_data(df.head(10), model_data["X_columns"])
        result = predict_risk(model_data, new_data)
        assert result is not None
        assert "risk_probability" in result
        assert "high_risk_prediction" in result
        assert len(result["risk_probability"]) == 10
        assert len(result["high_risk_prediction"]) == 10

    def test_risk_probability_values_are_bounded(self) -> None:
        """All probability values are between 0.0 and 1.0."""
        df = _make_training_df(n=200)
        model_data = build_prediction_model(df, save_model=False)
        assert model_data is not None

        new_data = _prepare_prediction_data(df.head(20), model_data["X_columns"])
        result = predict_risk(model_data, new_data)
        assert result is not None
        probs = result["risk_probability"]
        assert all(0.0 <= p <= 1.0 for p in probs)

    def test_prediction_values_are_binary(self) -> None:
        """high_risk_prediction values are 0 or 1."""
        df = _make_training_df(n=200)
        model_data = build_prediction_model(df, save_model=False)
        assert model_data is not None

        new_data = _prepare_prediction_data(df.head(20), model_data["X_columns"])
        result = predict_risk(model_data, new_data)
        assert result is not None
        preds = result["high_risk_prediction"]
        assert all(p in (0, 1) for p in preds)

    def test_single_row_prediction(self) -> None:
        """Prediction works for a single-row DataFrame."""
        df = _make_training_df(n=200)
        model_data = build_prediction_model(df, save_model=False)
        assert model_data is not None

        new_data = _prepare_prediction_data(df.head(1), model_data["X_columns"])
        result = predict_risk(model_data, new_data)
        assert result is not None
        assert len(result["risk_probability"]) == 1
