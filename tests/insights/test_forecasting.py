"""Tests for the lightweight forecasting module.

Verifies least squares trend fitting, extrapolation, the moving-average fallback for
short histories, the zero floor, and forecast summarization.
Pure tests over analysis.insights.forecasting.
"""

import pytest

from analysis.insights.forecasting import (
    METHOD_LINEAR_TREND,
    METHOD_MOVING_AVERAGE,
    EmptyHistoryError,
    forecast_values,
    linear_trend,
    moving_average,
    summarize_forecast,
)


def test_linear_trend_exaduration_line():
    slope, intercept = linear_trend([1.0, 3.0, 5.0, 7.0, 9.0])
    assert slope == pytest.approx(2.0)
    assert intercept == pytest.approx(1.0)


def test_linear_trend_flat_series():
    slope, _ = linear_trend([5.0, 5.0, 5.0, 5.0, 5.0])
    assert slope == pytest.approx(0.0)


def test_moving_average_uses_window_tail():
    assert moving_average([1.0, 2.0, 3.0, 4.0], window=2) == pytest.approx(3.5)


def test_forecast_uses_trend_with_enough_points():
    result = forecast_values([10.0, 12.0, 14.0, 16.0, 18.0], horizon=2)
    assert result["method"] == METHOD_LINEAR_TREND
    assert result["forecast"] == [20.0, 22.0]


def test_forecast_falls_back_to_moving_average():
    result = forecast_values([10.0, 20.0], horizon=3)
    assert result["method"] == METHOD_MOVING_AVERAGE
    assert result["forecast"] == [15.0, 15.0, 15.0]


def test_forecast_floors_at_zero():
    result = forecast_values([50.0, 40.0, 30.0, 20.0, 10.0], horizon=3)
    assert result["forecast"][-1] == 0.0


def test_forecast_rejects_empty_history():
    with pytest.raises(EmptyHistoryError):
        forecast_values([], horizon=5)
    with pytest.raises(EmptyHistoryError):
        forecast_values([1.0], horizon=0)


def test_summarize_forecast_change_vs_history():
    summary = summarize_forecast([20.0, 22.0], history_mean=14.0)
    assert summary["forecast_mean"] == 21.0
    assert summary["pct_change_vs_history"] == 50.0


def test_summarize_forecast_empty():
    summary = summarize_forecast([], history_mean=10.0)
    assert summary["forecast_mean"] is None
