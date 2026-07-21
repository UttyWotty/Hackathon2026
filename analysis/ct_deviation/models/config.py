"""
CT Deviation Models and Configuration.

This module contains data models and configuration for cycle time deviation analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

# ==================== Enums ==================== #


class DeviationCategory(Enum):
    """Categories for CT deviations based on percentage from target."""

    EXCELLENT = "Excellent (≤5% deviation)"
    GOOD = "Good (5-10% deviation)"
    ACCEPTABLE = "Acceptable (10-15% deviation)"
    POOR = "Poor (15-20% deviation)"
    CRITICAL = "Critical (>20% deviation)"


# ==================== Data Models ==================== #


@dataclass
class DeviationMetrics:
    """Data class to store comprehensive deviation metrics for an equipment.

    Attributes:
        equipment_code: Equipment identifier
        supplier_name: Supplier name
        total_shots: Total number of shots analyzed
        avg_ct: Average cycle time
        approved_ct: Approved/target cycle time
        ct_deviation: Absolute deviation from approved CT
        deviation_percentage: Deviation as percentage of approved CT
        deviation_category: Categorization of deviation severity
        shots_above_target: Number of shots exceeding target CT
        shots_below_target: Number of shots below target CT
        shots_on_target: Number of shots within acceptable range
        efficiency_score: Overall efficiency score (0-100)
        stability_score: Process stability score (0-100)
    """

    equipment_code: str
    supplier_name: str
    total_shots: int
    avg_ct: float
    approved_ct: float
    ct_deviation: float
    deviation_percentage: float
    deviation_category: DeviationCategory
    shots_above_target: int
    shots_below_target: int
    shots_on_target: int
    efficiency_score: float
    stability_score: float


# ==================== Configuration Constants ==================== #


# Deviation thresholds (percentages)
EXCELLENT_THRESHOLD = 5.0
GOOD_THRESHOLD = 10.0
ACCEPTABLE_THRESHOLD = 15.0
POOR_THRESHOLD = 20.0

# Statistical outlier detection parameters
Z_SCORE_THRESHOLD = 3.0  # Standard deviations for z-score outliers
IQR_MULTIPLIER = 1.5  # Multiplier for IQR method
ROLLING_WINDOW_SIZE = 50  # Window size for rolling deviation analysis

# On-target tolerance (percentage)
ON_TARGET_TOLERANCE = 5.0  # ±5% considered "on target"

# Colors for visualizations
CATEGORY_COLORS = {
    DeviationCategory.EXCELLENT: "#2ecc71",  # Green
    DeviationCategory.GOOD: "#3498db",  # Blue
    DeviationCategory.ACCEPTABLE: "#f39c12",  # Orange
    DeviationCategory.POOR: "#e67e22",  # Dark orange
    DeviationCategory.CRITICAL: "#e74c3c",  # Red
}


# ==================== Helper Functions ==================== #


def categorize_deviation(deviation_percentage: float) -> DeviationCategory:
    """Categorize a deviation percentage into a DeviationCategory.

    Args:
        deviation_percentage: Deviation as percentage (absolute value)

    Returns:
        DeviationCategory: Appropriate category for the deviation level
    """
    abs_deviation = abs(deviation_percentage)

    if abs_deviation <= EXCELLENT_THRESHOLD:
        return DeviationCategory.EXCELLENT
    elif abs_deviation <= GOOD_THRESHOLD:
        return DeviationCategory.GOOD
    elif abs_deviation <= ACCEPTABLE_THRESHOLD:
        return DeviationCategory.ACCEPTABLE
    elif abs_deviation <= POOR_THRESHOLD:
        return DeviationCategory.POOR
    else:
        return DeviationCategory.CRITICAL


def calculate_efficiency_score(
    shots_on_target: int, total_shots: int, deviation_percentage: float
) -> float:
    """Calculate an efficiency score based on shots on target and deviation.

    Args:
        shots_on_target: Number of shots within tolerance
        total_shots: Total number of shots
        deviation_percentage: Average deviation percentage

    Returns:
        float: Efficiency score from 0 to 100
    """
    if total_shots == 0:
        return 0.0

    # Base score from percentage of shots on target
    target_ratio = shots_on_target / total_shots
    base_score = target_ratio * 100

    # Penalty for high average deviation
    deviation_penalty = min(abs(deviation_percentage), 50) / 2  # Max 25 point penalty

    # Final score (clamped to 0-100)
    score = max(0, min(100, base_score - deviation_penalty))

    return round(score, 2)


def calculate_stability_score(std_dev: float, mean_ct: float) -> float:
    """Calculate a stability score based on coefficient of variation.

    Args:
        std_dev: Standard deviation of cycle times
        mean_ct: Mean cycle time

    Returns:
        float: Stability score from 0 to 100 (100 = most stable)
    """
    if mean_ct == 0:
        return 0.0

    # Calculate coefficient of variation (CV)
    cv = (std_dev / mean_ct) * 100

    # Convert CV to stability score (inverse relationship)
    # CV of 0% = score 100, CV of 20%+ = score 0
    stability = max(0, 100 - (cv * 5))

    return round(stability, 2)
