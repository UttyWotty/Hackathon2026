"""
Time-Windowed Tool Performance Comparison.

This module extends the tool comparison by slicing data into monthly windows,
showing how equipment rankings within the same approved CT group evolve over
time. Reveals whether performance gaps are stable (machine-inherent) or shift
(tooling wear, maintenance events, part revisions).
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

from .tool_comparison import (
    APPROVED_CT_TOLERANCE,
    MIN_EQUIPMENT_PER_GROUP,
    build_approved_ct_groups,
)

logger = logging.getLogger(__name__)

# Minimum shots per equipment per window to include
MIN_SHOTS_PER_WINDOW = 50

# Minimum windows an equipment must appear in to track trends
MIN_WINDOWS_FOR_TREND = 3


@dataclass
class ToolWindowStats:
    """One equipment's performance in one time window within a group.

    Attributes:
        equipment_code: Machine identifier
        tooling_type: Tooling type
        supplier_name: Supplier name
        window: The time window label (e.g. '2025-08')
        shot_count: Shots in this window
        mean_efficiency_pct: Mean efficiency in this window
        std_efficiency_pct: Std dev of efficiency in this window
        mean_ct: Average cycle time in seconds
        rank_in_window: Rank within the group for this window
        deviation_from_window_mean: Distance from group mean in this window
    """

    equipment_code: str
    tooling_type: str
    supplier_name: str
    window: str
    shot_count: int
    mean_efficiency_pct: float
    std_efficiency_pct: float
    mean_ct: float
    rank_in_window: int
    deviation_from_window_mean: float


@dataclass
class ToolTrendSummary:
    """How one equipment's performance trends over time within a group.

    Attributes:
        equipment_code: Machine identifier
        tooling_type: Tooling type
        windows_present: Number of windows this equipment appeared in
        mean_rank: Average rank across windows (lower = more consistently good)
        rank_std: Std of ranks (low = stable ranking, high = volatile)
        efficiency_trend: Slope of efficiency over time (pct points per month)
        best_window: Window label with highest efficiency
        worst_window: Window label with lowest efficiency
        best_efficiency: Efficiency in best window
        worst_efficiency: Efficiency in worst window
    """

    equipment_code: str
    tooling_type: str
    windows_present: int
    mean_rank: float
    rank_std: float
    efficiency_trend: float
    best_window: str
    worst_window: str
    best_efficiency: float
    worst_efficiency: float


@dataclass
class WindowedGroupResult:
    """Time-windowed comparison for one approved CT group.

    Attributes:
        approved_ct: The shared approved cycle time
        part_names: Parts in this group
        equipment_count: Total unique equipment across all windows
        window_count: Number of time windows
        window_stats: All per-equipment per-window stats
        trend_summaries: Per-equipment trend over time
        rankings_stable: Whether rankings are consistent across windows
    """

    approved_ct: float
    part_names: List[str]
    equipment_count: int
    window_count: int
    window_stats: List[ToolWindowStats]
    trend_summaries: List[ToolTrendSummary]
    rankings_stable: bool


# ==================== Windowing ==================== #


def _slice_into_months(df: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    """Slice DataFrame into monthly windows.

    Args:
        df: DataFrame with LOCAL_SHOT_TIME column

    Returns:
        Dict mapping 'YYYY-MM' to DataFrame
    """
    df = df.copy()
    df["window"] = df["LOCAL_SHOT_TIME"].dt.to_period("M").astype(str)

    windows = {}
    for window_label, window_df in df.groupby("window"):
        windows[str(window_label)] = window_df

    return windows


# ==================== Per-Window Analysis ==================== #


def _analyze_window(
    window_label: str,
    window_df: pd.DataFrame,
) -> List[ToolWindowStats]:
    """Analyze one time window within a group.

    Args:
        window_label: The window identifier (e.g. '2025-08')
        window_df: DataFrame for this window

    Returns:
        List of ToolWindowStats for equipment with enough data
    """
    stats = []
    for equip_code, equip_df in window_df.groupby("tool_id"):
        if len(equip_df) < MIN_SHOTS_PER_WINDOW:
            continue

        eff = equip_df["efficiency_pct"]
        tooling_type = (
            str(equip_df["TOOLING_TYPE"].iloc[0])
            if "TOOLING_TYPE" in equip_df.columns
            else "Unknown"
        )
        supplier_name = (
            str(equip_df["SUPPLIER_NAME"].iloc[0])
            if "SUPPLIER_NAME" in equip_df.columns
            else "Unknown"
        )

        stats.append(
            ToolWindowStats(
                equipment_code=str(equip_code),
                tooling_type=tooling_type,
                supplier_name=supplier_name,
                window=window_label,
                shot_count=len(equip_df),
                mean_efficiency_pct=round(float(eff.mean()), 2),
                std_efficiency_pct=round(float(eff.std()), 2),
                mean_ct=round(float(equip_df["CT"].mean()), 2),
                rank_in_window=0,
                deviation_from_window_mean=0.0,
            )
        )

    if len(stats) < MIN_EQUIPMENT_PER_GROUP:
        return []

    # Rank and calculate deviations within this window
    window_mean = float(np.mean([s.mean_efficiency_pct for s in stats]))
    for s in stats:
        s.deviation_from_window_mean = round(s.mean_efficiency_pct - window_mean, 2)

    stats.sort(key=lambda s: s.mean_efficiency_pct, reverse=True)
    for rank, s in enumerate(stats, start=1):
        s.rank_in_window = rank

    return stats


# ==================== Trend Calculation ==================== #


def _calculate_trends(
    all_stats: List[ToolWindowStats],
    sorted_windows: List[str],
) -> List[ToolTrendSummary]:
    """Calculate per-equipment trends across time windows.

    Args:
        all_stats: All window stats for this group
        sorted_windows: Window labels in chronological order

    Returns:
        List of ToolTrendSummary, sorted by mean_rank (best first)
    """
    # Group by equipment
    by_equip: Dict[str, List[ToolWindowStats]] = {}
    for s in all_stats:
        by_equip.setdefault(s.equipment_code, []).append(s)

    window_index = {w: i for i, w in enumerate(sorted_windows)}

    trends = []
    for equip_code, equip_stats in by_equip.items():
        if len(equip_stats) < MIN_WINDOWS_FOR_TREND:
            continue

        ranks = [s.rank_in_window for s in equip_stats]
        effs = [s.mean_efficiency_pct for s in equip_stats]

        # Simple linear trend: efficiency over window index
        x_vals = [window_index[s.window] for s in equip_stats]
        if len(set(x_vals)) >= 2:
            slope = float(np.polyfit(x_vals, effs, 1)[0])
        else:
            slope = 0.0

        best_stat = max(equip_stats, key=lambda s: s.mean_efficiency_pct)
        worst_stat = min(equip_stats, key=lambda s: s.mean_efficiency_pct)

        trends.append(
            ToolTrendSummary(
                equipment_code=equip_code,
                tooling_type=equip_stats[0].tooling_type,
                windows_present=len(equip_stats),
                mean_rank=round(float(np.mean(ranks)), 1),
                rank_std=round(float(np.std(ranks)), 1),
                efficiency_trend=round(slope, 3),
                best_window=best_stat.window,
                worst_window=worst_stat.window,
                best_efficiency=best_stat.mean_efficiency_pct,
                worst_efficiency=worst_stat.mean_efficiency_pct,
            )
        )

    trends.sort(key=lambda t: t.mean_rank)
    return trends


# ==================== Group-Level Windowed Analysis ==================== #


def analyze_group_windowed(
    approved_ct: float,
    group_df: pd.DataFrame,
) -> Optional[WindowedGroupResult]:
    """Run time-windowed comparison for one approved CT group.

    Args:
        approved_ct: The shared approved CT value
        group_df: DataFrame filtered to this group

    Returns:
        WindowedGroupResult or None if insufficient data
    """
    part_names = sorted(group_df["PART_NAME"].dropna().unique().astype(str).tolist())

    windows = _slice_into_months(group_df)
    sorted_window_labels = sorted(windows.keys())

    all_stats: List[ToolWindowStats] = []
    for label in sorted_window_labels:
        window_stats = _analyze_window(label, windows[label])
        all_stats.extend(window_stats)

    if not all_stats:
        return None

    # Count valid windows (those that produced stats)
    valid_windows = sorted(set(s.window for s in all_stats))
    unique_equipment = set(s.equipment_code for s in all_stats)

    if len(valid_windows) < MIN_WINDOWS_FOR_TREND:
        return None

    trends = _calculate_trends(all_stats, sorted_window_labels)

    # Rankings are stable if avg rank_std across equipment is < 1.0
    if trends:
        avg_rank_std = float(np.mean([t.rank_std for t in trends]))
        rankings_stable = avg_rank_std < 1.0
    else:
        rankings_stable = False

    return WindowedGroupResult(
        approved_ct=approved_ct,
        part_names=part_names,
        equipment_count=len(unique_equipment),
        window_count=len(valid_windows),
        window_stats=all_stats,
        trend_summaries=trends,
        rankings_stable=rankings_stable,
    )


# ==================== Batch Analysis ==================== #


def compare_tools_windowed(
    df: pd.DataFrame,
    tolerance: float = APPROVED_CT_TOLERANCE,
) -> List[WindowedGroupResult]:
    """Run time-windowed tool comparison across all approved CT groups.

    Args:
        df: Full DataFrame with efficiency_pct, CT, APPROVED_CT, tool_id,
            LOCAL_SHOT_TIME
        tolerance: CT grouping tolerance in seconds

    Returns:
        List of WindowedGroupResult, sorted by equipment count desc
    """
    logger.info("Running time-windowed tool comparison...")

    groups = build_approved_ct_groups(df, tolerance)

    results = []
    for ct_val, group_df in groups.items():
        result = analyze_group_windowed(ct_val, group_df)
        if result is not None:
            results.append(result)

    results.sort(key=lambda g: g.equipment_count, reverse=True)

    logger.info(
        "Windowed comparison complete: %d groups, %d total windows analyzed",
        len(results),
        sum(g.window_count for g in results),
    )

    return results
