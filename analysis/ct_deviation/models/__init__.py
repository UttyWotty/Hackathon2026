"""
CT Deviation Models Package.

Exports data models and configuration for CT deviation analysis.
"""

from .config import (
    ACCEPTABLE_THRESHOLD,
    CATEGORY_COLORS,
    EXCELLENT_THRESHOLD,
    GOOD_THRESHOLD,
    IQR_MULTIPLIER,
    ON_TARGET_TOLERANCE,
    POOR_THRESHOLD,
    ROLLING_WINDOW_SIZE,
    Z_SCORE_THRESHOLD,
    DeviationCategory,
    DeviationMetrics,
    calculate_efficiency_score,
    calculate_stability_score,
    categorize_deviation,
)

__all__ = [
    "DeviationCategory",
    "DeviationMetrics",
    "categorize_deviation",
    "calculate_efficiency_score",
    "calculate_stability_score",
    "EXCELLENT_THRESHOLD",
    "GOOD_THRESHOLD",
    "ACCEPTABLE_THRESHOLD",
    "POOR_THRESHOLD",
    "Z_SCORE_THRESHOLD",
    "IQR_MULTIPLIER",
    "ROLLING_WINDOW_SIZE",
    "ON_TARGET_TOLERANCE",
    "CATEGORY_COLORS",
]
