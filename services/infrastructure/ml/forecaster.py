"""
Forecasting Module.

Features:
- Time series forecasting (production, capacity)
- Linear regression forecasting
- Moving average forecasting
- Exponential smoothing
- Trend analysis

Author: Utku Gulbardak
Date: 2025-11-12
"""

import logging
from typing import Any, Dict, Optional, Tuple

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score

logger = logging.getLogger(__name__)


class Forecaster:
    """
    Forecasting for Manufacturing Metrics.

    Predicts future production, capacity, and performance.
    """

    def __init__(self):
        """Initialize Forecaster."""
        self.models = {}
        logger.info("✅ Forecaster initialized")

    def forecast_linear_trend(
        self,
        df: pd.DataFrame,
        time_col: str,
        value_col: str,
        periods_ahead: int = 30,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Forecast using linear regression.

        Args:
            df: Historical data
            time_col: Time column name
            value_col: Value column name
            periods_ahead: Number of periods to forecast

        Returns:
            tuple: (Forecast DataFrame, statistics)
        """
        # Sort by time
        df_sorted = df.sort_values(time_col).copy()

        # Create numeric time index
        df_sorted["time_index"] = range(len(df_sorted))

        # Prepare training data
        X = df_sorted[["time_index"]].values
        y = df_sorted[value_col].values

        # Train model
        model = LinearRegression()
        model.fit(X, y)

        # Make predictions on historical data
        y_pred = model.predict(X)

        # Calculate metrics
        mae = mean_absolute_error(y, y_pred)
        rmse = np.sqrt(mean_squared_error(y, y_pred))
        r2 = r2_score(y, y_pred)

        # Forecast future periods
        last_time_index = len(df_sorted)
        future_time_indices = np.array(
            [[i] for i in range(last_time_index, last_time_index + periods_ahead)]
        )
        future_predictions = model.predict(future_time_indices)

        # Create forecast dataframe
        forecast_df = pd.DataFrame(
            {
                "period": range(1, periods_ahead + 1),
                "forecast_value": future_predictions,
                "method": "linear_trend",
            }
        )

        return forecast_df, {
            "model": "linear_regression",
            "periods_forecasted": periods_ahead,
            "slope": float(model.coef_[0]),
            "intercept": float(model.intercept_),
            "mae": float(mae),
            "rmse": float(rmse),
            "r2_score": float(r2),
        }

    def forecast_moving_average(
        self,
        df: pd.DataFrame,
        time_col: str,
        value_col: str,
        window: int = 7,
        periods_ahead: int = 30,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Forecast using moving average.

        Args:
            df: Historical data
            time_col: Time column name
            value_col: Value column name
            window: Moving average window
            periods_ahead: Number of periods to forecast

        Returns:
            tuple: (Forecast DataFrame, statistics)
        """
        df_sorted = df.sort_values(time_col).copy()

        # Calculate moving average
        ma = df_sorted[value_col].rolling(window=window).mean()

        # Use last MA value as forecast (naive approach)
        last_ma = ma.iloc[-1]

        forecast_df = pd.DataFrame(
            {
                "period": range(1, periods_ahead + 1),
                "forecast_value": [last_ma] * periods_ahead,
                "method": "moving_average",
            }
        )

        return forecast_df, {
            "model": "moving_average",
            "window": window,
            "periods_forecasted": periods_ahead,
            "last_ma_value": float(last_ma),
        }

    def forecast_exponential_smoothing(
        self,
        df: pd.DataFrame,
        time_col: str,
        value_col: str,
        alpha: float = 0.3,
        periods_ahead: int = 30,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Forecast using exponential smoothing.

        Args:
            df: Historical data
            time_col: Time column name
            value_col: Value column name
            alpha: Smoothing factor (0-1)
            periods_ahead: Number of periods to forecast

        Returns:
            tuple: (Forecast DataFrame, statistics)
        """
        df_sorted = df.sort_values(time_col).copy()
        values = df_sorted[value_col].values

        # Apply exponential smoothing
        smoothed = [values[0]]  # Start with first value

        for i in range(1, len(values)):
            smoothed_value = alpha * values[i] + (1 - alpha) * smoothed[-1]
            smoothed.append(smoothed_value)

        # Forecast (use last smoothed value)
        last_smoothed = smoothed[-1]

        forecast_df = pd.DataFrame(
            {
                "period": range(1, periods_ahead + 1),
                "forecast_value": [last_smoothed] * periods_ahead,
                "method": "exponential_smoothing",
            }
        )

        return forecast_df, {
            "model": "exponential_smoothing",
            "alpha": alpha,
            "periods_forecasted": periods_ahead,
            "last_smoothed_value": float(last_smoothed),
        }

    def forecast_production_capacity(
        self,
        df: pd.DataFrame,
        equipment_code: str,
        date_col: str = "DATE",
        output_col: str = "TOTAL_OUTPUT",
        method: str = "linear_trend",
        periods_ahead: int = 30,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Forecast production capacity for equipment.

        Args:
            df: Historical production data
            equipment_code: Equipment code
            date_col: Date column name
            output_col: Output column name
            method: 'linear_trend', 'moving_average', or 'exponential_smoothing'
            periods_ahead: Days to forecast

        Returns:
            tuple: (Forecast DataFrame, statistics)
        """
        # Filter for equipment
        equipment_data = df[df["EQUIPMENT_CODE"] == equipment_code].copy()

        if len(equipment_data) < 2:
            raise ValueError(
                f"Insufficient data for {equipment_code}. Need at least 2 data points."
            )

        # Forecast based on method
        if method == "linear_trend":
            forecast_df, stats = self.forecast_linear_trend(
                equipment_data, date_col, output_col, periods_ahead
            )
        elif method == "moving_average":
            forecast_df, stats = self.forecast_moving_average(
                equipment_data, date_col, output_col, periods_ahead=periods_ahead
            )
        elif method == "exponential_smoothing":
            forecast_df, stats = self.forecast_exponential_smoothing(
                equipment_data, date_col, output_col, periods_ahead=periods_ahead
            )
        else:
            raise ValueError(f"Unknown method: {method}")

        # Add equipment info
        forecast_df["equipment_code"] = equipment_code

        stats["equipment_code"] = equipment_code
        stats["historical_periods"] = len(equipment_data)

        return forecast_df, stats

    def analyze_trend(
        self, df: pd.DataFrame, time_col: str, value_col: str
    ) -> Dict[str, Any]:
        """
        Analyze trend in time series data.

        Args:
            df: Time series data
            time_col: Time column name
            value_col: Value column name

        Returns:
            dict: Trend analysis
        """
        df_sorted = df.sort_values(time_col).copy()

        # Create numeric time index
        df_sorted["time_index"] = range(len(df_sorted))

        # Fit linear model
        X = df_sorted[["time_index"]].values
        y = df_sorted[value_col].values

        model = LinearRegression()
        model.fit(X, y)

        slope = model.coef_[0]

        # Determine trend direction
        if slope > 0.01:
            trend_direction = "increasing"
        elif slope < -0.01:
            trend_direction = "decreasing"
        else:
            trend_direction = "stable"

        # Calculate percentage change
        first_value = y[0]
        last_value = y[-1]
        pct_change = (
            ((last_value - first_value) / first_value * 100) if first_value != 0 else 0
        )

        return {
            "trend_direction": trend_direction,
            "slope": float(slope),
            "percentage_change": float(pct_change),
            "first_value": float(first_value),
            "last_value": float(last_value),
            "periods": len(df_sorted),
        }

    def forecast_timeseries(
        self,
        df: pd.DataFrame,
        target_column: str,
        periods: int = 30,
        time_column: str = "timestamp",
        frequency: str = "D",
        method: str = "linear_trend",
    ) -> Dict[str, Any]:
        """
        Forecast a time series column and return a unified result dict.

        This is the primary entry point used by the /ml/forecast endpoint.
        It delegates to the specific forecasting methods and normalises their
        output into the shape the router expects.

        Args:
            df: Historical data with at least time_column and target_column.
            target_column: Column to forecast.
            periods: Number of future periods.
            time_column: Name of the time/date column.
            frequency: Pandas frequency string (e.g. "D", "H").
            method: One of "linear_trend", "moving_average",
                    "exponential_smoothing", "seasonal".

        Returns:
            Dict with keys "forecast", "confidence_intervals", "model_info".
        """
        method_map = {
            "linear_trend": self.forecast_linear_trend,
            "moving_average": self.forecast_moving_average,
            "exponential_smoothing": self.forecast_exponential_smoothing,
            "seasonal": self.forecast_with_seasonality,
        }

        forecast_fn = method_map.get(method)
        if forecast_fn is None:
            raise ValueError(
                f"Unknown method '{method}'. Choose from: {list(method_map)}"
            )

        forecast_df, stats = forecast_fn(
            df=df,
            time_col=time_column,
            value_col=target_column,
            periods_ahead=periods,
        )

        forecast_records = forecast_df.to_dict(orient="records")

        return {
            "forecast": forecast_records,
            "confidence_intervals": {},
            "model_info": stats,
        }

    def forecast_with_seasonality(
        self,
        df: pd.DataFrame,
        time_col: str,
        value_col: str,
        season_period: int = 7,
        periods_ahead: int = 30,
    ) -> Tuple[pd.DataFrame, Dict[str, Any]]:
        """
        Simple seasonal forecast using historical averages.

        Args:
            df: Historical data
            time_col: Time column name
            value_col: Value column name
            season_period: Length of seasonal cycle (e.g., 7 for weekly)
            periods_ahead: Periods to forecast

        Returns:
            tuple: (Forecast DataFrame, statistics)
        """
        df_sorted = df.sort_values(time_col).copy()

        # Calculate seasonal averages
        df_sorted["season_index"] = df_sorted.index % season_period
        seasonal_avg = df_sorted.groupby("season_index")[value_col].mean()

        # Generate forecasts using seasonal pattern
        forecast_values = []
        for i in range(periods_ahead):
            season_idx = i % season_period
            forecast_values.append(seasonal_avg[season_idx])

        forecast_df = pd.DataFrame(
            {
                "period": range(1, periods_ahead + 1),
                "forecast_value": forecast_values,
                "method": "seasonal",
            }
        )

        return forecast_df, {
            "model": "seasonal_average",
            "season_period": season_period,
            "periods_forecasted": periods_ahead,
            "seasonal_averages": seasonal_avg.to_dict(),
        }


# Global forecaster instance
_forecaster: Optional[Forecaster] = None


def get_forecaster() -> Forecaster:
    """
    Get global forecaster instance.

    Returns:
        Forecaster: Global forecaster instance
    """
    global _forecaster
    if _forecaster is None:
        _forecaster = Forecaster()
    return _forecaster
