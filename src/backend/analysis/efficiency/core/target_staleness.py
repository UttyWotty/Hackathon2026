"""
Approved Duration Staleness Detector.

This module analyzes whether TARGET_DURATION baselines are still valid by detecting
consistent efficiency degradation over time. When all machines in a group trend
negative at similar rates, the problem is not the machines -- the baseline is stale.
"""

import logging
from dataclasses import dataclass
from typing import List, Optional

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from .tool_comparison import TARGET_DURATION_TOLERANCE, build_target_duration_groups

logger = logging.getLogger(__name__)

# Minimum months of data to assess staleness
MIN_MONTHS_FOR_STALENESS = 3

# Minimum shots per month for a month to count
MIN_SHOTS_PER_MONTH = 100

# Threshold: if group trend is worse than this per month, flag as stale
STALENESS_TREND_THRESHOLD = -0.3  # pct points per month

# If the latest month efficiency is below this, the baseline is clearly wrong
SEVERE_UNDERPERFORMANCE_THRESHOLD = -15.0  # pct


@dataclass
class MonthSnapshot:
    """Efficiency snapshot for one month across all equipment in a group.

    Attributes:
        window: Month label (YYYY-MM)
        equipment_count: Equipment active this month
        total_shots: Shots across all equipment
        group_mean_efficiency: Mean efficiency across equipment
        group_median_efficiency: Median efficiency
        group_std_efficiency: Spread across equipment
        mean_duration: Average actual duration
    """

    window: str
    equipment_count: int
    total_shots: int
    group_mean_efficiency: float
    group_median_efficiency: float
    group_std_efficiency: float
    mean_duration: float


@dataclass
class StalenessResult:
    """Staleness assessment for one approved duration group.

    Attributes:
        target_duration: The approved duration value
        product_names: Parts in this group
        months_analyzed: Number of months with sufficient data
        monthly_snapshots: Per-month group-level stats
        trend_per_month: Slope of group mean efficiency over time
        latest_efficiency: Most recent month's group mean efficiency
        earliest_efficiency: First month's group mean efficiency
        total_drift: latest - earliest efficiency
        is_stale: Whether the baseline appears stale
        severity: 'ok', 'warning', 'stale', 'severely_stale'
        suggested_duration: What the approved duration should be based on actual performance
        reasoning: Human-readable explanation
    """

    target_duration: float
    product_names: List[str]
    months_analyzed: int
    monthly_snapshots: List[MonthSnapshot]
    trend_per_month: float
    latest_efficiency: float
    earliest_efficiency: float
    total_drift: float
    is_stale: bool
    severity: str
    suggested_duration: float
    reasoning: str


# ==================== Monthly Aggregation ==================== #


def _aggregate_monthly(
    group_df: pd.DataFrame,
) -> List[MonthSnapshot]:
    """Aggregate group data into monthly snapshots.

    Args:
        group_df: DataFrame for one approved duration group

    Returns:
        List of MonthSnapshot in chronological order
    """
    df = group_df.copy()
    df["window"] = df["SHOT_TIME"].dt.to_period("M").astype(str)

    snapshots = []
    for window_label, month_df in df.groupby("window"):
        if len(month_df) < MIN_SHOTS_PER_MONTH:
            continue

        eff = month_df["efficiency_pct"]
        snapshots.append(
            MonthSnapshot(
                window=str(window_label),
                equipment_count=month_df["tool_id"].nunique(),
                total_shots=len(month_df),
                group_mean_efficiency=round(float(eff.mean()), 2),
                group_median_efficiency=round(float(eff.median()), 2),
                group_std_efficiency=round(float(eff.std()), 2),
                mean_duration=round(float(month_df["DURATION"].mean()), 2),
            )
        )

    snapshots.sort(key=lambda s: s.window)
    return snapshots


# ==================== Staleness Assessment ==================== #


def _calculate_suggested_duration(
    target_duration: float,
    latest_mean_duration: float,
    latest_efficiency: float,
) -> float:
    """Calculate what the approved duration should be based on recent performance.

    Uses the latest month's actual mean duration as the realistic baseline,
    with a small target buffer (2% improvement target).

    Args:
        target_duration: Current approved duration
        latest_mean_duration: Most recent month's average actual duration
        latest_efficiency: Most recent efficiency percentage

    Returns:
        Suggested approved duration in seconds
    """
    # Target: 2% better than current actual performance
    target_improvement = 0.02
    suggested = latest_mean_duration * (1.0 - target_improvement)
    return round(suggested, 1)


def assess_group_staleness(
    target_duration: float,
    group_df: pd.DataFrame,
) -> Optional[StalenessResult]:
    """Assess whether the approved duration for a group is stale.

    Args:
        target_duration: The approved duration value
        group_df: DataFrame filtered to this group

    Returns:
        StalenessResult or None if insufficient data
    """
    product_names = sorted(
        group_df["PRODUCT_NAME"].dropna().unique().astype(str).tolist()
    )

    snapshots = _aggregate_monthly(group_df)
    if len(snapshots) < MIN_MONTHS_FOR_STALENESS:
        return None

    # Calculate trend
    monthly_means = [s.group_mean_efficiency for s in snapshots]
    x_vals = list(range(len(monthly_means)))

    if len(set(monthly_means)) < 2:
        trend = 0.0
    else:
        trend = float(np.polyfit(x_vals, monthly_means, 1)[0])

    latest = snapshots[-1]
    earliest = snapshots[0]
    total_drift = latest.group_mean_efficiency - earliest.group_mean_efficiency

    # Determine severity
    severity = _classify_severity(trend, latest.group_mean_efficiency)
    is_stale = severity in ("stale", "severely_stale")

    suggested_duration = _calculate_suggested_duration(
        target_duration, latest.mean_duration, latest.group_mean_efficiency
    )

    reasoning = _build_reasoning(
        target_duration,
        severity,
        trend,
        latest,
        earliest,
        total_drift,
        suggested_duration,
    )

    return StalenessResult(
        target_duration=target_duration,
        product_names=product_names,
        months_analyzed=len(snapshots),
        monthly_snapshots=snapshots,
        trend_per_month=round(trend, 3),
        latest_efficiency=latest.group_mean_efficiency,
        earliest_efficiency=earliest.group_mean_efficiency,
        total_drift=round(total_drift, 2),
        is_stale=is_stale,
        severity=severity,
        suggested_duration=suggested_duration,
        reasoning=reasoning,
    )


UNDERPERFORMANCE_THRESHOLD = -8.0  # Below this = baseline is questionable


def _classify_severity(trend: float, latest_efficiency: float) -> str:
    """Classify staleness severity.

    Args:
        trend: Efficiency trend per month
        latest_efficiency: Most recent month's efficiency

    Returns:
        Severity string
    """
    if latest_efficiency < SEVERE_UNDERPERFORMANCE_THRESHOLD:
        if trend < STALENESS_TREND_THRESHOLD:
            return "severely_stale"
        return "stale"
    elif latest_efficiency < UNDERPERFORMANCE_THRESHOLD:
        if trend < STALENESS_TREND_THRESHOLD:
            return "stale"
        return "warning"
    elif trend < STALENESS_TREND_THRESHOLD:
        return "warning"
    return "ok"


def _build_reasoning(
    target_duration: float,
    severity: str,
    trend: float,
    latest: MonthSnapshot,
    earliest: MonthSnapshot,
    total_drift: float,
    suggested_duration: float,
) -> str:
    """Build human-readable explanation of staleness assessment.

    Args:
        target_duration: Current approved duration
        severity: Classified severity
        trend: Monthly trend
        latest: Latest month snapshot
        earliest: Earliest month snapshot
        total_drift: Total efficiency change
        suggested_duration: Recommended Duration

    Returns:
        Explanation string
    """
    if severity == "ok":
        return (
            f"Approved Duration {target_duration}s appears valid. "
            f"Latest efficiency: {latest.group_mean_efficiency}%, "
            f"trend: {trend:.2f}%/month."
        )

    drift_direction = "degraded" if total_drift < 0 else "improved"
    len([s for s in [earliest, latest]])  # placeholder
    # Calculate months between earliest and latest
    months_span = (int(latest.window[:4]) - int(earliest.window[:4])) * 12 + (
        int(latest.window[5:7]) - int(earliest.window[5:7])
    )
    return (
        f"Approved Duration {target_duration}s is {severity.replace('_', ' ')}. "
        f"Performance {drift_direction} from {earliest.group_mean_efficiency}% "
        f"({earliest.window}) to {latest.group_mean_efficiency}% ({latest.window}), "
        f"drift of {round(total_drift, 2)}% over {months_span} months. "
        f"Trend: {trend:.2f}%/month. "
        f"Actual mean duration is {latest.mean_duration}s vs approved {target_duration}s. "
        f"Suggested revised duration: {suggested_duration}s."
    )


# ==================== Batch Analysis ==================== #


def detect_stale_baselines(
    df: pd.DataFrame,
    tolerance: float = TARGET_DURATION_TOLERANCE,
) -> List[StalenessResult]:
    """Detect stale approved duration baselines across all groups.

    Args:
        df: Full DataFrame with efficiency_pct, duration, TARGET_DURATION, SHOT_TIME
        tolerance: duration grouping tolerance

    Returns:
        List of StalenessResult, stale groups first
    """
    logger.info("Detecting stale approved duration baselines...")

    groups = build_target_duration_groups(df, tolerance)

    results = []
    for ct_val, group_df in groups.items():
        result = assess_group_staleness(ct_val, group_df)
        if result is not None:
            results.append(result)

    # Sort: severely stale first, then stale, then warning, then ok
    severity_order = {"severely_stale": 0, "stale": 1, "warning": 2, "ok": 3}
    results.sort(key=lambda r: (severity_order.get(r.severity, 4), r.trend_per_month))

    stale_count = sum(1 for r in results if r.is_stale)
    logger.info(
        "Staleness detection complete: %d groups analyzed, %d stale",
        len(results),
        stale_count,
    )

    return results
