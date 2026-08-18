"""
ROI Analysis Configuration
===========================

Configuration classes and constants for ROI analysis.

Author: Utku Gulbardak
Date: 2025-10-24
"""

from dataclasses import dataclass


@dataclass
class ROIAnalysisConfig:
    """
    Configuration class for ROI analysis parameters (daily aggregation level).

    Attributes:
        delta_tolerance: ±% tolerance for duration classification (default: 0.05 = 5%)
        min_shots_threshold: Minimum shots per day required for valid analysis
        min_efficiency_threshold: Minimum efficiency for valid data
        max_efficiency_threshold: Maximum efficiency for valid data
    """

    delta_tolerance: float = 0.05  # ±5% tolerance for duration classification
    min_shots_threshold: int = (
        10  # Minimum shots per day for valid analysis (lowered for daily)
    )
    min_efficiency_threshold: float = 10.0  # Minimum efficiency for valid data
    max_efficiency_threshold: float = 300.0  # Maximum efficiency for valid data
