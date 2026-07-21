"""Configuration models for RunRate analysis."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class RunRateConfig:
    """
    Configuration for RunRate analysis.

    Attributes:
        equipment_code: Equipment code to analyze (REQUIRED)
        supplier_name: Optional supplier name filter
        start_date: Optional start date for analysis
        end_date: Optional end date for analysis
        output_dir: Optional directory for output files
        enable_charts: Whether to generate charts (default: True)
        ct_filter_threshold: Filter out CT values above this (default: 999)
        stop_detection_threshold: Threshold for stop detection in hours (default: 8)
        mode_ct_tolerance: Tolerance for mode CT (±%) (default: 0.05 = 5%)
    """

    equipment_code: str
    supplier_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    output_dir: Optional[str] = None
    enable_charts: bool = True
    ct_filter_threshold: float = 999.0
    stop_detection_threshold: float = 8.0  # hours
    mode_ct_tolerance: float = 0.05  # 5%

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.equipment_code:
            raise ValueError("equipment_code is required")

        # Validate dates if provided
        if self.start_date:
            try:
                datetime.strptime(self.start_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("start_date must be in YYYY-MM-DD format")

        if self.end_date:
            try:
                datetime.strptime(self.end_date, "%Y-%m-%d")
            except ValueError:
                raise ValueError("end_date must be in YYYY-MM-DD format")

        # Validate thresholds
        if self.ct_filter_threshold <= 0:
            raise ValueError("ct_filter_threshold must be positive")

        if self.stop_detection_threshold <= 0:
            raise ValueError("stop_detection_threshold must be positive")

        if not 0 < self.mode_ct_tolerance < 1:
            raise ValueError("mode_ct_tolerance must be between 0 and 1")
