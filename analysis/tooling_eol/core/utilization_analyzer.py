"""
Tooling EOL Utilization Analyzer.

This module handles capacity and utilization calculations for tooling
end-of-life prediction.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import logging
from typing import Iterable, Tuple

import numpy as np
import pandas as pd

from ..models.config import SECONDS_PER_WEEK, get_oee

# Configure logging
logger = logging.getLogger(__name__)


# ==================== Capacity & Utilization ==================== #


def compute_capacity_and_utilization(
    mold_df: pd.DataFrame,
    weekly_shots: float,
) -> Tuple[float, float]:
    """Compute ideal weekly capacity (shots) and utilization percent.

    Ideal weekly capacity is derived from APPROVED_CT as 604800 / approved_ct
    (seconds per week divided by seconds per shot). If APPROVED_CT is missing,
    capacity defaults to NaN and utilization cannot be computed.

    Args:
        mold_df: Subset for single mold including 'APPROVED_CT'.
        weekly_shots: Average weekly shots.

    Returns:
        Tuple of (ideal_weekly_capacity, utilization_percent)
    """
    if mold_df.empty:
        return np.nan, np.nan

    # Prefer MOLD table capacity when present: weekly capacity = daily_max_capacity * production_days
    ideal_capacity = np.nan
    if "DAILY_MAX_CAPACITY" in mold_df.columns and "PRODUCTION_DAYS" in mold_df.columns:
        daily_cap = mold_df["DAILY_MAX_CAPACITY"].dropna().median()
        prod_days = mold_df["PRODUCTION_DAYS"].dropna().median()
        if (
            np.isfinite(daily_cap)
            and np.isfinite(prod_days)
            and daily_cap > 0
            and prod_days > 0
        ):
            ideal_capacity = float(daily_cap * prod_days)

    # Fallback to APPROVED_CT-derived capacity if not available
    if not np.isfinite(ideal_capacity):
        if "APPROVED_CT" not in mold_df.columns:
            return np.nan, np.nan
        approved_ct = mold_df["APPROVED_CT"].dropna().median()
        if not np.isfinite(approved_ct) or approved_ct <= 0:
            return np.nan, np.nan
        # seconds in a week / seconds per shot
        ideal_capacity = float(SECONDS_PER_WEEK / approved_ct)

    # Apply OEE factor depending on tooling type. TOOLING_TYPE may be null/empty,
    # in which case tooling_family stays None and get_oee falls back to a default.
    tooling_family = None
    if "TOOLING_TYPE" in mold_df.columns and mold_df["TOOLING_TYPE"].notna().any():
        tooling_family = str(mold_df["TOOLING_TYPE"].dropna().mode().iloc[0])
    oee = get_oee(tooling_family)
    ideal_capacity = ideal_capacity * oee

    utilization_pct = (
        (weekly_shots / ideal_capacity) * 100.0 if ideal_capacity > 0 else np.nan
    )
    return float(ideal_capacity), float(utilization_pct)


def categorize_utilization(
    utilization_pct: float, bins: Iterable[int] = (0, 30, 80, 100)
) -> str:
    """Categorize utilization percent into Low/Medium/High/Overutilized.

    Args:
        utilization_pct: Utilization value in percent (0-100+).
        bins: Thresholds defining categories [0, 30, 80, 100].

    Returns:
        str: One of ['Low','Medium','High','Overutilized','Unknown'].
    """
    if not np.isfinite(utilization_pct):
        return "Unknown"

    b0, b1, b2, b3 = list(bins)
    if utilization_pct < b1:
        return "Low"
    if utilization_pct < b2:
        return "Medium"
    if utilization_pct <= b3:
        return "High"
    return "Overutilized"
