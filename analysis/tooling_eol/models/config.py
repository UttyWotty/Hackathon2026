"""
Tooling EOL Models and Configuration.

This module contains data models and configuration constants for tooling
end-of-life prediction.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

import pandas as pd

# ==================== Data Models ==================== #


@dataclass
class ELCPrediction:
    """Container for end-of-life prediction outputs for a mold.

    Attributes:
        mold_id: Unique mold identifier
        equipment_code: Equipment code associated with the mold
        latest_shot_time: Most recent shot timestamp
        current_shots_observed: Total observed shot count
        weekly_rate: Average shots per week
        ideal_weekly_capacity: Theoretical maximum weekly capacity
        utilization_pct: Current utilization percentage
        utilization_category: Utilization category (Low/Medium/High/Overutilized)
        design_shot_life: Design life in total shots
        life_consumption_pct: Percentage of design life consumed
        remaining_shots: Estimated shots remaining
        remaining_days: Estimated days until EOL
        predicted_eol_date: Predicted end-of-life date
        confidence: Confidence level (High/Medium/Low/Very Low)
        confidence_pct: Numeric confidence percentage
        seasonal_flag: Whether seasonal pattern detected
        overutilization_weeks_streak: Consecutive weeks of overutilization
        warnings: Any warnings or alerts
        history_coverage_pct: Historical data coverage percentage
        recency_pct: Recency score for data
        stability_pct: Rate stability score
        maintenance_applied: Whether maintenance reset was applied
        maintenance_date: Date of last maintenance
        maintenance_source: Source of maintenance data
        maintenance_warning: Maintenance-related warnings
        candidate_refurb_dates: Potential refurbishment dates
    """

    mold_id: int
    equipment_code: Optional[str]
    latest_shot_time: Optional[pd.Timestamp]
    current_shots_observed: int
    weekly_rate: float
    ideal_weekly_capacity: Optional[float]
    utilization_pct: Optional[float]
    utilization_category: str
    design_shot_life: int
    life_consumption_pct: Optional[float]
    remaining_shots: Optional[int]
    remaining_days: Optional[float]
    predicted_eol_date: Optional[pd.Timestamp]
    confidence: str
    confidence_pct: Optional[float]
    seasonal_flag: Optional[bool]
    overutilization_weeks_streak: Optional[int]
    warnings: Optional[str]
    # Confidence components for transparency
    history_coverage_pct: Optional[float]
    recency_pct: Optional[float]
    stability_pct: Optional[float]
    # Maintenance fields
    maintenance_applied: Optional[bool] = None
    maintenance_date: Optional[pd.Timestamp] = None
    maintenance_source: Optional[str] = None
    maintenance_warning: Optional[str] = None
    candidate_refurb_dates: Optional[str] = None


# ==================== Configuration Constants ==================== #


def get_oee(tooling_family: Optional[str] = None) -> float:
    """Return an OEE factor (0-1) by tooling family with env overrides.

    Defaults are conservative and can be overridden via environment variables.

    Args:
        tooling_family: Optional tooling family name

    Returns:
        float: OEE factor between 0 and 1
    """
    default_oee = float(os.getenv("DEFAULT_OEE", "0.7"))
    if not tooling_family:
        return default_oee

    mapping: Dict[str, float] = {
        "Injection Molding": float(os.getenv("INJECTION_MOLDING_OEE", "0.75")),
        "Die Casting": float(os.getenv("DIE_CASTING_OEE", "0.65")),
        "Stamping": float(os.getenv("STAMPING_OEE", "0.60")),
    }
    return mapping.get(tooling_family, default_oee)


def get_utilization_bins(
    tooling_family: Optional[str] = None,
) -> Tuple[int, int, int, int]:
    """Return utilization bins tuned per tooling family.

    Returns bins as (low_threshold, medium_threshold, high_threshold, max_threshold).
    Values are percentages.

    Args:
        tooling_family: Optional tooling family name

    Returns:
        Tuple of 4 integers defining utilization thresholds
    """
    if not tooling_family:
        return (0, 30, 80, 100)

    family_bins: Dict[str, Tuple[int, int, int, int]] = {
        "Injection Molding": (0, 50, 85, 100),
        "Die Casting": (0, 40, 80, 100),
        "Stamping": (0, 30, 60, 90),
    }
    return family_bins.get(tooling_family, (0, 30, 80, 100))


def get_derate_factor(tooling_family: Optional[str] = None) -> float:
    """Design life derate factor (0-1) by tooling family with env overrides.

    Args:
        tooling_family: Optional tooling family name

    Returns:
        float: Derate factor between 0 and 1
    """
    default_factor = float(os.getenv("DEFAULT_DESIGN_LIFE_DERATE", "0.8"))
    if not tooling_family:
        return default_factor

    mapping: Dict[str, float] = {
        "Injection Molding": float(os.getenv("INJECTION_MOLDING_DERATE", "0.85")),
        "Die Casting": float(os.getenv("DIE_CASTING_DERATE", "0.8")),
        "Stamping": float(os.getenv("STAMPING_DERATE", "0.75")),
    }
    return mapping.get(tooling_family, default_factor)


def get_design_life(tooling_family: Optional[str] = None) -> int:
    """Select a design life in shots based on tooling family.

    Defaults are intentionally conservative and must be calibrated.

    Args:
        tooling_family: Optional tooling family name

    Returns:
        int: Design life in number of shots

    Note:
        NOTE: Per-mold limits can be configured in database if needed.
    """
    default_life = int(os.getenv("DEFAULT_TOOLING_DESIGN_LIFE_SHOTS", "1000000"))
    if not tooling_family:
        return default_life

    mapping: Dict[str, int] = {
        # Based on current domain knowledge
        "Injection Molding": int(
            os.getenv("INJECTION_MOLDING_DESIGN_LIFE_SHOTS", "1500000")
        ),
        "Die Casting": int(os.getenv("DIE_CASTING_DESIGN_LIFE_SHOTS", "800000")),
        "Stamping": int(os.getenv("STAMPING_DESIGN_LIFE_SHOTS", "500000")),
    }
    return mapping.get(tooling_family, default_life)


# ==================== Constants ==================== #

# Time constants
SECONDS_PER_WEEK = 604800.0  # 7 days * 24 hours * 60 minutes * 60 seconds

# Analysis windows
DEFAULT_RECENT_WEEKS = 12  # Default window for weekly rate calculation
DEFAULT_SEASONALITY_MONTHS = 12  # Months to check for seasonality

# Confidence thresholds (in weeks of history)
CONFIDENCE_HIGH_WEEKS = 26  # 6 months
CONFIDENCE_MEDIUM_WEEKS = 12  # 3 months
CONFIDENCE_LOW_WEEKS = 4  # 1 month

# Utilization categories
UTILIZATION_LOW = "Low"
UTILIZATION_MEDIUM = "Medium"
UTILIZATION_HIGH = "High"
UTILIZATION_OVERUTILIZED = "Overutilized"
UTILIZATION_UNKNOWN = "Unknown"
