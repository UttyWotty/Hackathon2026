"""Lightweight time series forecasting via linear trend and moving average.

Fits an ordinary least squares trend line to a value series and extrapolates it over a
horizon, falling back to the moving average when the history is too short for a fit.
Pure logic with no numpy/sklearn dependency so it is fully deterministic and testable.
"""

from typing import Any, Dict, List, Optional, Tuple

MIN_POINTS_FOR_TREND: int = 5
DEFAULT_MOVING_AVERAGE_WINDOW: int = 7
FORECAST_FLOOR: float = 0.0
FORECAST_PRECISION: int = 2

METHOD_LINEAR_TREND: str = "linear_trend"
METHOD_MOVING_AVERAGE: str = "moving_average"


class EmptyHistoryError(ValueError):
    """Raised when forecasting is requested with no historical values."""


def linear_trend(values: List[float]) -> Tuple[float, float]:
    """Fit y = slope * x + intercept over indices 0..n-1 by least squares.

    Args:
        values: Historical values, oldest first. Must contain at least 2 points.

    Returns:
        Tuple of (slope, intercept).
    """
    n = len(values)
    mean_x = (n - 1) / 2.0
    mean_y = sum(values) / n
    sxx = sum((i - mean_x) ** 2 for i in range(n))
    sxy = sum((i - mean_x) * (values[i] - mean_y) for i in range(n))
    slope = sxy / sxx if sxx else 0.0
    return slope, mean_y - slope * mean_x


def moving_average(
    values: List[float], window: int = DEFAULT_MOVING_AVERAGE_WINDOW
) -> float:
    """Average of the last `window` values (or all values when shorter)."""
    tail = values[-window:] if window > 0 else values
    return sum(tail) / len(tail)


def forecast_values(
    values: List[float],
    horizon: int,
    window: int = DEFAULT_MOVING_AVERAGE_WINDOW,
) -> Dict[str, Any]:
    """Forecast the next `horizon` values from a history.

    Uses a linear trend when at least MIN_POINTS_FOR_TREND points exist, otherwise
    repeats the moving average. Forecasts are floored at zero (production metrics
    cannot go negative).

    Args:
        values: Historical values, oldest first.
        horizon: Number of future points to forecast (must be positive).
        window: Moving average window for the fallback (default: 7).

    Returns:
        dict with method, forecast list, slope_per_step, and history_mean.

    Raises:
        EmptyHistoryError: When values is empty or horizon is not positive.
    """
    if not values or horizon <= 0:
        raise EmptyHistoryError("Forecast requires non-empty history and horizon > 0")

    history_mean = round(sum(values) / len(values), FORECAST_PRECISION)

    if len(values) >= MIN_POINTS_FOR_TREND:
        slope, intercept = linear_trend(values)
        start = len(values)
        forecast = [
            round(
                max(FORECAST_FLOOR, slope * (start + step) + intercept),
                FORECAST_PRECISION,
            )
            for step in range(horizon)
        ]
        return {
            "method": METHOD_LINEAR_TREND,
            "forecast": forecast,
            "slope_per_step": round(slope, 4),
            "history_mean": history_mean,
        }

    level = round(
        max(FORECAST_FLOOR, moving_average(values, window)), FORECAST_PRECISION
    )
    return {
        "method": METHOD_MOVING_AVERAGE,
        "forecast": [level] * horizon,
        "slope_per_step": 0.0,
        "history_mean": history_mean,
    }


def summarize_forecast(
    forecast: List[float], history_mean: Optional[float]
) -> Dict[str, Any]:
    """Summarize a forecast against the historical mean.

    Args:
        forecast: Forecasted values.
        history_mean: Mean of the history (None skips the change calculation).

    Returns:
        dict with forecast_mean and pct_change_vs_history (None when undefined).
    """
    if not forecast:
        return {"forecast_mean": None, "pct_change_vs_history": None}
    forecast_mean = round(sum(forecast) / len(forecast), FORECAST_PRECISION)
    pct: Optional[float] = None
    if history_mean:
        pct = round((forecast_mean - history_mean) / abs(history_mean) * 100.0, 2)
    return {"forecast_mean": forecast_mean, "pct_change_vs_history": pct}
