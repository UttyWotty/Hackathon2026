"""
Automatic Shift Boundary Detector (Per-Supplier).

This module detects shift change times per supplier by analyzing shot rate
patterns. Different plants/suppliers have different schedules (2 or 3 shifts,
different hours). Detects from data rather than assuming.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Tuple

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

MIN_SHOTS_FOR_DETECTION = 5000
MIN_DIP_RATIO = 0.6
# If the trough between two peaks holds > this ratio of peak, it's not a real dip
NIGHT_ACTIVITY_THRESHOLD = 0.4  # Below this = no real night shift


@dataclass
class DetectedShifts:
    """Result of automatic shift boundary detection for one supplier.

    Attributes:
        vendor_name: Which supplier this applies to
        num_shifts: Detected number of shifts (2 or 3)
        boundaries: List of hours where shifts start
        labels: Human-readable labels for each shift
        confidence: How clear the pattern is (0-1)
        hourly_shot_counts: Normalized shot counts per hour (for charting)
        dip_hours: Hours identified as transition points
        method: Detection method used
        night_activity: Normalized shot rate during overnight hours (0-1)
    """

    vendor_name: str
    num_shifts: int
    boundaries: List[int]
    labels: List[str]
    confidence: float
    hourly_shot_counts: List[Tuple[int, float]]
    dip_hours: List[int]
    method: str
    night_activity: float = 0.0


def _build_hourly_profile(df: pd.DataFrame) -> pd.Series:
    """Build normalized shot count profile by hour of day.

    Args:
        df: DataFrame with SHOT_TIME column

    Returns:
        Series indexed by hour (0-23) with normalized shot counts (0-1)
    """
    df = df.copy()
    df["hour"] = df["SHOT_TIME"].dt.hour
    df["date"] = df["SHOT_TIME"].dt.date

    daily_hourly = df.groupby(["date", "hour"]).size().reset_index(name="count")
    avg_by_hour = daily_hourly.groupby("hour")["count"].mean()

    full_hours = pd.Series(0.0, index=range(24))
    full_hours.update(avg_by_hour)

    max_val = full_hours.max()
    if max_val > 0:
        full_hours = full_hours / max_val

    return full_hours


def _find_dips(profile: pd.Series) -> List[Tuple[int, float]]:
    """Find local minima in the hourly profile.

    Args:
        profile: Normalized hourly shot counts

    Returns:
        List of (hour, depth) tuples sorted by depth descending
    """
    values = profile.values
    n = len(values)
    dips = []

    for i in range(n):
        prev_idx = (i - 1) % n
        next_idx = (i + 1) % n

        if values[i] < values[prev_idx] and values[i] < values[next_idx]:
            if values[i] < MIN_DIP_RATIO:
                depth = 1.0 - values[i]
                dips.append((i, depth))

    dips.sort(key=lambda x: x[1], reverse=True)
    return dips


def _assess_night_activity(profile: pd.Series) -> float:
    """Check how active the overnight hours (22-06) are.

    Args:
        profile: Normalized hourly profile

    Returns:
        Mean normalized activity during 22:00-05:59
    """
    night_hours = list(range(22, 24)) + list(range(0, 6))
    night_vals = [profile.iloc[h] for h in night_hours]
    return float(np.mean(night_vals))


def _detect_for_supplier(
    vendor_name: str,
    supplier_df: pd.DataFrame,
) -> DetectedShifts:
    """Detect shift boundaries for one supplier.

    Logic:
    1. Build hourly profile
    2. Find all dips
    3. Check night activity to determine 2 vs 3 shifts
    4. Select appropriate boundaries

    Args:
        vendor_name: Supplier identifier
        supplier_df: Data filtered to this supplier

    Returns:
        DetectedShifts for this supplier
    """
    if len(supplier_df) < MIN_SHOTS_FOR_DETECTION:
        return DetectedShifts(
            vendor_name=vendor_name,
            num_shifts=2,
            boundaries=[6, 18],
            labels=["Shift A (06-18)", "Shift B (18-06)"],
            confidence=0.0,
            hourly_shot_counts=[],
            dip_hours=[],
            method="default_fallback_low_data",
            night_activity=0.0,
        )

    profile = _build_hourly_profile(supplier_df)
    hourly_counts = [(int(h), round(float(v), 3)) for h, v in profile.items()]

    dips = _find_dips(profile)
    dip_hours = [h for h, _ in dips]

    night_activity = _assess_night_activity(profile)

    # Determine 2 vs 3 shifts
    if night_activity < NIGHT_ACTIVITY_THRESHOLD:
        # Low night activity = 2-shift operation
        # Find the single deepest dip during daytime (typically around shift change)
        num_shifts = 2
        # Look for dips between 10-18 (mid-day change) or use the deepest dip
        if dips:
            # Take the deepest dip as the mid-day boundary
            # Plus an early-morning boundary where production starts
            day_start = _find_production_start(profile)
            mid_dip = dips[0][0]

            # If the deepest dip is overnight, skip it and take next daytime dip
            daytime_dips = [(h, d) for h, d in dips if 8 <= h <= 20]
            if daytime_dips:
                mid_dip = daytime_dips[0][0]
                boundaries = sorted([day_start, mid_dip])
            else:
                boundaries = [day_start, (day_start + 12) % 24]
        else:
            day_start = _find_production_start(profile)
            boundaries = [day_start, (day_start + 12) % 24]

    else:
        # Night is active = 3-shift operation
        num_shifts = 3
        if len(dips) >= 3:
            boundaries = sorted([h for h, _ in dips[:3]])
        elif len(dips) == 2:
            boundaries = sorted([h for h, _ in dips[:2]])
            # Add a third boundary 8 hours after the first
            third = (boundaries[0] + 8) % 24
            boundaries = sorted(set(boundaries + [third]))[:3]
        else:
            boundaries = [6, 14, 22]

    labels = _generate_labels(boundaries)

    # Confidence
    if dips:
        used_dips = [d for h, d in dips if h in boundaries]
        confidence = round(min(1.0, float(np.mean(used_dips)) if used_dips else 0.5), 2)
    else:
        confidence = 0.0

    logger.info(
        "Supplier %s: %d shifts at %s (night_activity=%.2f, confidence=%.2f)",
        vendor_name,
        num_shifts,
        boundaries,
        night_activity,
        confidence,
    )

    return DetectedShifts(
        vendor_name=vendor_name,
        num_shifts=num_shifts,
        boundaries=boundaries,
        labels=labels,
        confidence=confidence,
        hourly_shot_counts=hourly_counts,
        dip_hours=dip_hours,
        method="per_supplier_detection",
        night_activity=round(night_activity, 3),
    )


def _find_production_start(profile: pd.Series) -> int:
    """Find the hour where production ramps up from overnight low.

    Args:
        profile: Normalized hourly profile

    Returns:
        Hour of day where production starts (typically 5-8)
    """
    values = profile.values
    # Look for the steepest rise between hours 3-9
    max_rise = 0
    start_hour = 6

    for h in range(3, 10):
        rise = values[h] - values[h - 1]
        if rise > max_rise:
            max_rise = rise
            start_hour = h

    return start_hour


def _generate_labels(boundaries: List[int]) -> List[str]:
    """Generate shift labels from boundaries.

    Args:
        boundaries: Sorted shift start hours

    Returns:
        List of labels
    """
    labels = []
    n = len(boundaries)
    for i in range(n):
        start = boundaries[i]
        end = boundaries[(i + 1) % n]
        labels.append(f"Shift {chr(65 + i)} ({start:02d}-{end:02d})")
    return labels


# ==================== Main Entry Points ==================== #


def detect_shift_boundaries(
    df: pd.DataFrame,
    max_shifts: int = 3,
) -> DetectedShifts:
    """Detect shift boundaries for the entire dataset (global).

    Args:
        df: Full DataFrame with SHOT_TIME
        max_shifts: Maximum shifts (unused, kept for API compat)

    Returns:
        DetectedShifts for the overall dataset
    """
    return _detect_for_supplier("ALL", df)


def detect_shifts_per_supplier(
    df: pd.DataFrame,
) -> Dict[str, DetectedShifts]:
    """Detect shift boundaries separately for each supplier.

    Args:
        df: Full DataFrame with SHOT_TIME and VENDOR_NAME

    Returns:
        Dict mapping supplier name to DetectedShifts
    """
    results = {}
    for vendor_name, supplier_df in df.groupby("VENDOR_NAME"):
        result = _detect_for_supplier(str(vendor_name), supplier_df)
        results[str(vendor_name)] = result

    logger.info(
        "Detected shifts for %d suppliers: %s",
        len(results),
        {s: r.num_shifts for s, r in results.items()},
    )

    return results
