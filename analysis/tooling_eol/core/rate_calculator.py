"""
Tooling EOL Rate Calculator.

This module handles weekly rate calculation and seasonality detection
for tooling end-of-life prediction.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

# Configure logging
logger = logging.getLogger(__name__)


# ==================== Rate Calculation ==================== #


def calculate_weekly_rate(mold_df: pd.DataFrame, recent_weeks: int = 12) -> float:
    """Calculate an average weekly shots rate using recent active weeks.

    - Aggregates shots by week start date (Monday) and sums shots per week
    - Excludes weeks with zero production
    - Uses the last `recent_weeks` active weeks if available; otherwise uses all

    Args:
        mold_df: Subset for a single mold; requires 'SHOT_TIME' and 'SHOT_COUNT'.
        recent_weeks: Number of most recent active weeks to average over.

    Returns:
        float: Average shots per week. Returns 0.0 if insufficient data.
    """
    if mold_df.empty or "SHOT_TIME" not in mold_df.columns:
        return 0.0

    tmp = mold_df.dropna(subset=["SHOT_TIME"]).copy()
    if tmp.empty:
        return 0.0

    tmp["WEEK_START"] = tmp["SHOT_TIME"].dt.to_period("W-MON").dt.start_time
    weekly = tmp.groupby("WEEK_START")["SHOT_COUNT"].sum().replace(0, np.nan).dropna()
    if weekly.empty:
        return 0.0

    weekly = weekly.sort_index()
    if recent_weeks and weekly.shape[0] > recent_weeks:
        weekly = weekly.iloc[-recent_weeks:]

    # Weighted moving average: more recent weeks get higher weight
    weights = np.arange(1, len(weekly) + 1, dtype=float)
    try:
        wavg = float(np.average(weekly.values, weights=weights))
    except ZeroDivisionError:
        wavg = float(weekly.mean())
    return wavg


# ==================== Seasonality Detection ==================== #


def detect_seasonality(weekly: pd.Series, months_window: int = 12) -> bool:
    """Detect seasonality: if activity is clustered in few months.

    Returns True if active months < 1/3 of the window.

    Args:
        weekly: Series indexed by week with shot counts
        months_window: Number of months to analyze

    Returns:
        bool: True if seasonal pattern detected
    """
    if weekly is None or weekly.empty:
        return False
    # Map weeks to months
    idx = pd.to_datetime(weekly.index)
    months = pd.PeriodIndex(idx, freq="M")
    # Consider last N months
    if len(months) > months_window:
        months = months[-months_window:]
    active_months = pd.Index(months.unique()).size
    return active_months < max(1, months_window // 3)


def count_active_months(weekly: pd.Series, months_window: int = 12) -> int:
    """Count unique active months in the last N months of a weekly series index.

    Args:
        weekly: Series indexed by week with shot counts
        months_window: Number of months to analyze

    Returns:
        int: Count of unique active months
    """
    if weekly is None or weekly.empty:
        return 0
    idx = pd.to_datetime(weekly.index)
    months = pd.PeriodIndex(idx, freq="M")
    if len(months) > months_window:
        months = months[-months_window:]
    return pd.Index(months.unique()).size
