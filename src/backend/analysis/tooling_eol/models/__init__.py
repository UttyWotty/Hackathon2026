"""
Tooling EOL Models Package.

Exports data models and configuration for tooling end-of-life prediction.
"""

from .config import (
    CONFIDENCE_HIGH_WEEKS,
    CONFIDENCE_LOW_WEEKS,
    CONFIDENCE_MEDIUM_WEEKS,
    DEFAULT_RECENT_WEEKS,
    DEFAULT_SEASONALITY_MONTHS,
    SECONDS_PER_WEEK,
    UTILIZATION_HIGH,
    UTILIZATION_LOW,
    UTILIZATION_MEDIUM,
    UTILIZATION_OVERUTILIZED,
    UTILIZATION_UNKNOWN,
    ELCPrediction,
    get_derate_factor,
    get_design_life,
    get_oee,
    get_utilization_bins,
)

__all__ = [
    "ELCPrediction",
    "get_oee",
    "get_utilization_bins",
    "get_derate_factor",
    "get_design_life",
    "SECONDS_PER_WEEK",
    "DEFAULT_RECENT_WEEKS",
    "DEFAULT_SEASONALITY_MONTHS",
    "CONFIDENCE_HIGH_WEEKS",
    "CONFIDENCE_MEDIUM_WEEKS",
    "CONFIDENCE_LOW_WEEKS",
    "UTILIZATION_LOW",
    "UTILIZATION_MEDIUM",
    "UTILIZATION_HIGH",
    "UTILIZATION_OVERUTILIZED",
    "UTILIZATION_UNKNOWN",
]
