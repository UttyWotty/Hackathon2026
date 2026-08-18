"""
Shift Performance Analyzer - Daily Granularity.

This module segments production data into daily shift instances to compare
operator performance. Each date+shift is treated as a unique operator instance
since operators rotate across shifts. Analyzes whether day-to-day variance
within shifts indicates operator impact on machine performance.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from ..models import MIN_SHOTS_PER_SESSION

logger = logging.getLogger(__name__)

# Default shift boundaries observed from shot rate analysis (HPDC machines)
DEFAULT_SHIFT_BOUNDARIES = [6, 14, 22]  # 6am, 2pm, 10pm
SHIFT_LABELS = ["Night (22-06)", "Morning (06-14)", "Afternoon (14-22)"]

# Minimum shots in a single daily shift instance to count
MIN_SHOTS_PER_DAILY_SHIFT = 50

# Minimum daily shift instances to draw conclusions
MIN_DAILY_INSTANCES = 5

# Threshold for "performance differs" (std of daily means in pct points)
OPERATOR_IMPACT_THRESHOLD_PCT = 1.5


@dataclass
class DailyShiftInstance:
    """One operator's shift on one day for one equipment.

    Attributes:
        date: The calendar date
        shift_label: Which shift window
        shot_count: Number of shots produced
        mean_efficiency_pct: Average efficiency during this instance
        median_efficiency_pct: Median efficiency
        std_efficiency_pct: Std dev of efficiency within this instance
        mean_duration: Average duration in seconds
        first_20_efficiency_pct: Efficiency of first 20 shots (transition)
        steady_efficiency_pct: Efficiency after first 20 shots
    """

    date: str
    shift_label: str
    shot_count: int
    mean_efficiency_pct: float
    median_efficiency_pct: float
    std_efficiency_pct: float
    mean_duration: float
    first_20_efficiency_pct: float
    steady_efficiency_pct: float


@dataclass
class ShiftSummary:
    """Aggregated stats for one shift window across all days.

    Attributes:
        shift_label: Which shift window
        total_instances: Number of daily instances observed
        total_shots: Total shots across all instances
        mean_of_daily_means: Average of per-day mean efficiencies
        std_of_daily_means: Day-to-day variance (operator signal)
        median_of_daily_means: Median of per-day means
        min_daily_mean: Worst single day
        max_daily_mean: Best single day
        mean_transition_penalty: Avg first-20-shot penalty across days
    """

    shift_label: str
    total_instances: int
    total_shots: int
    mean_of_daily_means: float
    std_of_daily_means: float
    median_of_daily_means: float
    min_daily_mean: float
    max_daily_mean: float
    mean_transition_penalty: float


@dataclass
class VarianceDecomposition:
    """Within-day (shift/operator) vs across-day (tooling/part) variance.

    Attributes:
        within_day_std: Avg std of shift means within the same day (operator signal)
        across_day_std: Std of daily means across different days (tooling/time signal)
        operator_ratio: within_day_std / across_day_std (0=machine dominates, 1=operators matter)
        days_with_all_shifts: Number of days that had all 3 shifts for comparison
        conclusion: Human-readable verdict
    """

    within_day_std: float
    across_day_std: float
    operator_ratio: float
    days_with_all_shifts: int
    conclusion: str


@dataclass
class EquipmentShiftAnalysis:
    """Complete daily shift analysis for one equipment.

    Attributes:
        machine_id: Machine identifier
        process_type: Tooling type classification
        vendor_name: Supplier name
        daily_instances: All daily shift instances (raw data)
        shift_summaries: Aggregated stats per shift window
        overall_daily_std: Std of daily means across ALL shifts
        operator_impact: Whether day-to-day variance suggests operator impact
        best_day: Date+shift with highest efficiency
        worst_day: Date+shift with lowest efficiency
        variance: Decomposed variance analysis (operator vs machine)
    """

    machine_id: str
    process_type: str
    vendor_name: str
    daily_instances: List[DailyShiftInstance]
    shift_summaries: List[ShiftSummary]
    overall_daily_std: float
    operator_impact: bool
    best_day: str
    worst_day: str
    variance: Optional[VarianceDecomposition] = None


# ==================== Shift Assignment ==================== #


def assign_shift(hour: int, boundaries: List[int] = None) -> int:
    """Assign a shift index based on hour-of-day.

    Args:
        hour: Hour of day (0-23)
        boundaries: Shift start hours (default [6, 14, 22])

    Returns:
        Shift index (0=Night, 1=Morning, 2=Afternoon)
    """
    if boundaries is None:
        boundaries = DEFAULT_SHIFT_BOUNDARIES

    for i in range(len(boundaries) - 1, -1, -1):
        if hour >= boundaries[i]:
            return i
    return len(boundaries) - 1


# ==================== Daily Instance Extraction ==================== #


TRANSITION_SHOT_COUNT = 20


def extract_daily_instances(
    df: pd.DataFrame,
    boundaries: List[int] = None,
) -> List[DailyShiftInstance]:
    """Extract per-day per-shift performance instances from equipment data.

    Args:
        df: DataFrame with SHOT_TIME, efficiency_pct, DURATION columns
        boundaries: Shift start hours

    Returns:
        List of DailyShiftInstance, one per date+shift with enough data
    """
    if boundaries is None:
        boundaries = DEFAULT_SHIFT_BOUNDARIES

    df = df.copy()
    df["shot_hour"] = df["SHOT_TIME"].dt.hour
    df["shift_index"] = df["shot_hour"].apply(lambda h: assign_shift(h, boundaries))
    df["shift_label"] = df["shift_index"].map(
        {i: SHIFT_LABELS[i] for i in range(len(SHIFT_LABELS))}
    )
    df["shot_date"] = df["SHOT_TIME"].dt.date

    instances = []
    for (date, shift_label), group in df.groupby(["shot_date", "shift_label"]):
        if len(group) < MIN_SHOTS_PER_DAILY_SHIFT:
            continue

        sorted_group = group.sort_values("SHOT_TIME")
        eff = sorted_group["efficiency_pct"]

        first_20_eff = (
            eff.iloc[:TRANSITION_SHOT_COUNT].mean()
            if len(eff) >= TRANSITION_SHOT_COUNT
            else eff.mean()
        )
        steady_eff = (
            eff.iloc[TRANSITION_SHOT_COUNT:].mean()
            if len(eff) > TRANSITION_SHOT_COUNT
            else eff.mean()
        )

        instance = DailyShiftInstance(
            date=str(date),
            shift_label=str(shift_label),
            shot_count=len(group),
            mean_efficiency_pct=round(float(eff.mean()), 2),
            median_efficiency_pct=round(float(eff.median()), 2),
            std_efficiency_pct=round(float(eff.std()), 2),
            mean_duration=round(float(group["DURATION"].mean()), 2),
            first_20_efficiency_pct=round(float(first_20_eff), 2),
            steady_efficiency_pct=round(float(steady_eff), 2),
        )
        instances.append(instance)

    return instances


# ==================== Shift Summary ==================== #


def summarize_shifts(instances: List[DailyShiftInstance]) -> List[ShiftSummary]:
    """Aggregate daily instances into per-shift summaries.

    Args:
        instances: List of DailyShiftInstance

    Returns:
        List of ShiftSummary, one per shift that has enough data
    """
    by_shift: Dict[str, List[DailyShiftInstance]] = {}
    for inst in instances:
        by_shift.setdefault(inst.shift_label, []).append(inst)

    summaries = []
    for label, shift_instances in by_shift.items():
        if len(shift_instances) < MIN_DAILY_INSTANCES:
            continue

        daily_means = [i.mean_efficiency_pct for i in shift_instances]
        transition_penalties = [
            i.steady_efficiency_pct - i.first_20_efficiency_pct for i in shift_instances
        ]

        summary = ShiftSummary(
            shift_label=label,
            total_instances=len(shift_instances),
            total_shots=sum(i.shot_count for i in shift_instances),
            mean_of_daily_means=round(float(np.mean(daily_means)), 2),
            std_of_daily_means=round(float(np.std(daily_means)), 2),
            median_of_daily_means=round(float(np.median(daily_means)), 2),
            min_daily_mean=round(float(min(daily_means)), 2),
            max_daily_mean=round(float(max(daily_means)), 2),
            mean_transition_penalty=round(float(np.mean(transition_penalties)), 2),
        )
        summaries.append(summary)

    return summaries


# ==================== Equipment-Level Analysis ==================== #


def decompose_variance(
    instances: List[DailyShiftInstance],
) -> Optional[VarianceDecomposition]:
    """Decompose performance variance into within-day (operator) and across-day (machine).

    For each day that has all 3 shifts, calculates the std of the 3 shift means.
    That within-day std captures shift/operator differences.
    Across-day std (of daily averages) captures tooling wear, part changes, etc.

    The ratio (within / across) tells the story:
    - < 0.3 = machine dominates, operators are interchangeable
    - 0.3-0.7 = mixed, some operator effect
    - > 0.7 = operators significantly impact performance

    Args:
        instances: List of DailyShiftInstance

    Returns:
        VarianceDecomposition or None if insufficient multi-shift days
    """
    # Group instances by date
    by_date: Dict[str, List[DailyShiftInstance]] = {}
    for inst in instances:
        by_date.setdefault(inst.date, []).append(inst)

    # Only use days with all 3 shifts for fair comparison
    full_days = {d: insts for d, insts in by_date.items() if len(insts) >= 3}

    if len(full_days) < 3:
        return None

    # Within-day: for each full day, std of the shift means
    within_day_stds = []
    daily_means = []
    for date, insts in full_days.items():
        shift_means = [i.mean_efficiency_pct for i in insts]
        within_day_stds.append(float(np.std(shift_means)))
        daily_means.append(float(np.mean(shift_means)))

    avg_within_day_std = float(np.mean(within_day_stds))
    across_day_std = float(np.std(daily_means))

    # Calculate ratio (avoid division by zero)
    if across_day_std > 0:
        ratio = avg_within_day_std / across_day_std
    else:
        ratio = 0.0 if avg_within_day_std == 0 else 1.0

    ratio = min(ratio, 2.0)  # Cap at 2.0 for readability

    # Determine conclusion
    if ratio < 0.3:
        conclusion = "Machine dominates. Operators are interchangeable."
    elif ratio < 0.7:
        conclusion = (
            "Mixed signal. Some operator effect, but machine/tooling is primary driver."
        )
    else:
        conclusion = "Operators significantly impact performance across shifts."

    return VarianceDecomposition(
        within_day_std=round(avg_within_day_std, 3),
        across_day_std=round(across_day_std, 3),
        operator_ratio=round(ratio, 3),
        days_with_all_shifts=len(full_days),
        conclusion=conclusion,
    )


def analyze_equipment_shifts(
    equip_df: pd.DataFrame,
    machine_id: str,
    boundaries: List[int] = None,
) -> Optional[EquipmentShiftAnalysis]:
    """Run daily shift performance analysis for one equipment.

    Args:
        equip_df: DataFrame filtered to one equipment
        machine_id: Equipment identifier
        boundaries: Shift start hours

    Returns:
        EquipmentShiftAnalysis or None if insufficient data
    """
    process_type = (
        str(equip_df["TYPE"].iloc[0])
        if "TYPE" in equip_df.columns
        else "Unknown"
    )
    vendor_name = (
        str(equip_df["VENDOR_NAME"].iloc[0])
        if "VENDOR_NAME" in equip_df.columns
        else "Unknown"
    )

    instances = extract_daily_instances(equip_df, boundaries)
    if len(instances) < MIN_DAILY_INSTANCES:
        return None

    shift_summaries = summarize_shifts(instances)
    if not shift_summaries:
        return None

    all_daily_means = [i.mean_efficiency_pct for i in instances]
    overall_std = float(np.std(all_daily_means))

    # Variance decomposition: within-day (operator) vs across-day (machine)
    variance = decompose_variance(instances)

    # Use variance ratio for operator_impact instead of raw threshold
    if variance is not None:
        operator_impact = variance.operator_ratio >= 0.3
    else:
        operator_impact = overall_std > OPERATOR_IMPACT_THRESHOLD_PCT

    best_inst = max(instances, key=lambda i: i.mean_efficiency_pct)
    worst_inst = min(instances, key=lambda i: i.mean_efficiency_pct)
    best_day = f"{best_inst.date} {best_inst.shift_label}"
    worst_day = f"{worst_inst.date} {worst_inst.shift_label}"

    return EquipmentShiftAnalysis(
        machine_id=machine_id,
        process_type=process_type,
        vendor_name=vendor_name,
        daily_instances=instances,
        shift_summaries=shift_summaries,
        overall_daily_std=round(overall_std, 2),
        operator_impact=operator_impact,
        best_day=best_day,
        worst_day=worst_day,
        variance=variance,
    )


# ==================== Batch Analysis ==================== #


def analyze_all_equipment_shifts(
    df: pd.DataFrame,
    boundaries: List[int] = None,
    min_total_shots: int = MIN_SHOTS_PER_SESSION,
) -> List[EquipmentShiftAnalysis]:
    """Run daily shift analysis across all equipment.

    Args:
        df: Full DataFrame with efficiency_pct, duration, SHOT_TIME, tool_id
        boundaries: Shift start hours
        min_total_shots: Minimum total shots for equipment to be included

    Returns:
        List of EquipmentShiftAnalysis results
    """
    logger.info("Analyzing daily shift performance across all equipment...")

    results = []
    for equip_code, equip_df in df.groupby("tool_id"):
        if len(equip_df) < min_total_shots:
            continue

        analysis = analyze_equipment_shifts(equip_df, str(equip_code), boundaries)
        if analysis is not None:
            results.append(analysis)

    impact_count = sum(1 for r in results if r.operator_impact)
    logger.info(
        "Daily shift analysis complete: %d equipment, %d show operator impact",
        len(results),
        impact_count,
    )

    return results
