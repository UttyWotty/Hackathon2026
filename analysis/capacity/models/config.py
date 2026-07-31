"""
Configuration for Capacity Analysis.

Defines configuration constants, equipment mappings, and configuration dataclass
for capacity and OEE analysis.

Author: Utku Gulbardak
Date: 2025-10-27
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    import pandas as pd  # type: ignore[import-untyped]


# Default analysis parameters
DEFAULT_EQUIPMENT_CODE: str = "MX-7102"
DEFAULT_SUPPLIER_NAME: str = "Vantis industries SCS"
DEFAULT_START_DATE: str = "2025-03-08 00:00:00"
DEFAULT_END_DATE: str = "2025-08-31 23:59:59"

# Default OEE targets for multi-OEE analysis (50% to 100% in 10% increments)
DEFAULT_OEE_TARGETS: List[float] = [0.50, 0.60, 0.70, 0.80, 0.90, 1.00]

# Equipment code to cavity count mapping (1 shot = N parts)
# Multi-cavity molds produce multiple parts per shot
# NOTE: These are HARDCODED because system has incorrect VOLUME data for these equipment
# For all other equipment, cavity count is calculated from VOLUME column
EQUIPMENT_CAVITY_MAPPING: dict = {
    "MX-7101": 4,  # 1 shot, 4 parts (hardcoded - system has wrong data)
    "MX-7102": 4,  # 1 shot, 4 parts (hardcoded - system has wrong data)
    "3BD3008371": 2,  # 1 shot, 2 parts (hardcoded - system has wrong data)
    "3BD3008451": 2,  # 1 shot, 2 parts (hardcoded - system has wrong data)
}

# Session quality thresholds
MIN_SHOTS_PER_SESSION: int = 10  # Filter out sessions with fewer shots

# Stop detection parameters
STOP_DETECTION_THRESHOLD_HOURS: float = (
    8.0  # Don't count breaks longer than 8 hours as stops
)
MODE_CT_TOLERANCE: float = 0.05  # ±5% tolerance for mode CT in stop detection


@dataclass
class CapacityConfig:
    """
    Configuration for Capacity/OEE analysis.

    Attributes:
        equipment_code: Equipment code to analyze (REQUIRED)
        supplier_name: Optional supplier name filter
        start_date: Analysis start date (YYYY-MM-DD HH:MM:SS)
        end_date: Analysis end date (YYYY-MM-DD HH:MM:SS)
        oee_targets: List of OEE target percentages (e.g., [0.50, 0.60, ..., 1.00])
        output_dir: Optional directory for output files
        enable_dashboard: Whether to generate HTML dashboard (default: True)
        enable_excel: Whether to generate Excel report (default: True)
        min_shots_per_session: Minimum shots required for a session to be included
        stop_threshold_hours: Maximum gap duration to be counted as a stop (hours)
        mode_ct_tolerance: Tolerance for mode CT in stop detection (±%)
    """

    equipment_code: str
    supplier_name: Optional[str] = None
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    oee_targets: Optional[List[float]] = None
    output_dir: Optional[str] = None
    enable_dashboard: bool = True
    enable_excel: bool = True
    min_shots_per_session: int = MIN_SHOTS_PER_SESSION
    stop_threshold_hours: float = STOP_DETECTION_THRESHOLD_HOURS
    mode_ct_tolerance: float = MODE_CT_TOLERANCE

    def __post_init__(self):
        """Validate configuration after initialization."""
        if not self.equipment_code:
            raise ValueError("equipment_code is required")

        # Set default OEE targets if not provided
        if self.oee_targets is None:
            self.oee_targets = DEFAULT_OEE_TARGETS.copy()

        # Validate OEE targets are between 0 and 1
        for target in self.oee_targets:
            if not 0 < target <= 1:
                raise ValueError(f"OEE target {target} must be between 0 and 1")

        # Set default dates if not provided
        if not self.start_date:
            self.start_date = DEFAULT_START_DATE
        if not self.end_date:
            self.end_date = DEFAULT_END_DATE

    def get_cavity_count(self, data: Optional["pd.DataFrame"] = None) -> int:
        """
        Get cavity count for the configured equipment.

        Args:
            data: Optional DataFrame with VOLUME column to calculate cavity count

        Returns:
            int: Number of parts produced per shot
        """
        # Import inside method to avoid circular import
        from ..core.data_processor import get_cavity_count

        return get_cavity_count(self.equipment_code, data=data)
