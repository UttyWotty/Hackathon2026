"""
Tool Performance Comparison Within Same-Part Groups.

This module groups equipment by APPROVED_CT (same approved CT = same or similar
parts) and compares their cycle time efficiency within each group. This provides
a fair ground-truth benchmark: machines doing the same job, compared head-to-head.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np  # type: ignore[import-untyped]
import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# Minimum shots per equipment in a group to include in comparison
MIN_SHOTS_FOR_COMPARISON = 200

# Minimum equipment in a group to make comparison meaningful
MIN_EQUIPMENT_PER_GROUP = 2

# Tolerance for grouping approved CTs (seconds) - exact match by default
APPROVED_CT_TOLERANCE = 0.0


@dataclass
class ToolInGroup:
    """One equipment's performance within an approved CT group.

    Attributes:
        equipment_code: Machine identifier
        tooling_type: Tooling type
        supplier_name: Supplier name
        shot_count: Total shots for this equipment in this group
        mean_efficiency_pct: Mean efficiency (APPROVED_CT / CT - 1) * 100
        median_efficiency_pct: Median efficiency
        std_efficiency_pct: Std dev of efficiency (consistency)
        mean_ct: Average actual cycle time
        rank_in_group: Rank within group (1 = best)
        deviation_from_group_mean: How far from group average (pct points)
    """

    equipment_code: str
    tooling_type: str
    supplier_name: str
    shot_count: int
    mean_efficiency_pct: float
    median_efficiency_pct: float
    std_efficiency_pct: float
    mean_ct: float
    rank_in_group: int
    deviation_from_group_mean: float


@dataclass
class ApprovedCTGroup:
    """A group of equipment sharing the same APPROVED_CT (same part).

    Attributes:
        approved_ct: The shared approved cycle time (seconds)
        part_ids: Unique PART_IDs seen in this group
        part_names: Unique PART_NAMEs seen in this group
        equipment_count: Number of equipment in the group
        total_shots: Total shots across all equipment
        group_mean_efficiency: Average efficiency across all equipment
        group_std_efficiency: Std of equipment means (spread of performance)
        tools: List of per-equipment stats, ranked best to worst
    """

    approved_ct: float
    part_ids: List[str]
    part_names: List[str]
    equipment_count: int
    total_shots: int
    group_mean_efficiency: float
    group_std_efficiency: float
    tools: List[ToolInGroup]


# ==================== Grouping ==================== #


def build_approved_ct_groups(
    df: pd.DataFrame,
    tolerance: float = APPROVED_CT_TOLERANCE,
) -> Dict[float, pd.DataFrame]:
    """Group data by APPROVED_CT value.

    Args:
        df: DataFrame with APPROVED_CT, tool_id, efficiency_pct columns
        tolerance: Tolerance for CT matching (0 = exact match)

    Returns:
        Dict mapping approved_ct value to DataFrame of shots in that group
    """
    if tolerance == 0.0:
        # Exact match: round to 2 decimal places to handle float precision
        df = df.copy()
        df["ct_group"] = df["APPROVED_CT"].round(2)
    else:
        # Bucket by tolerance
        df = df.copy()
        df["ct_group"] = (df["APPROVED_CT"] / tolerance).round(0) * tolerance

    groups = {}
    for ct_val, group_df in df.groupby("ct_group"):
        # Only keep groups with enough equipment
        equip_count = group_df["tool_id"].nunique()
        if equip_count >= MIN_EQUIPMENT_PER_GROUP:
            groups[float(ct_val)] = group_df

    logger.info(
        "Found %d approved CT groups with >= %d equipment",
        len(groups),
        MIN_EQUIPMENT_PER_GROUP,
    )

    return groups


# ==================== Per-Group Analysis ==================== #


def analyze_group(
    approved_ct: float,
    group_df: pd.DataFrame,
) -> Optional[ApprovedCTGroup]:
    """Analyze equipment performance within one approved CT group.

    Args:
        approved_ct: The shared approved CT value
        group_df: DataFrame filtered to this group

    Returns:
        ApprovedCTGroup or None if insufficient data
    """
    # Collect part info
    part_ids = sorted(group_df["PART_ID"].dropna().unique().astype(str).tolist())
    part_names = sorted(group_df["PART_NAME"].dropna().unique().astype(str).tolist())

    # Per-equipment stats
    tool_stats = []
    for equip_code, equip_df in group_df.groupby("tool_id"):
        if len(equip_df) < MIN_SHOTS_FOR_COMPARISON:
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

        tool_stats.append(
            ToolInGroup(
                equipment_code=str(equip_code),
                tooling_type=tooling_type,
                supplier_name=supplier_name,
                shot_count=len(equip_df),
                mean_efficiency_pct=round(float(eff.mean()), 2),
                median_efficiency_pct=round(float(eff.median()), 2),
                std_efficiency_pct=round(float(eff.std()), 2),
                mean_ct=round(float(equip_df["CT"].mean()), 2),
                rank_in_group=0,  # Set after sorting
                deviation_from_group_mean=0.0,  # Set after group mean calc
            )
        )

    if len(tool_stats) < MIN_EQUIPMENT_PER_GROUP:
        return None

    # Group-level stats
    equipment_means = [t.mean_efficiency_pct for t in tool_stats]
    group_mean = float(np.mean(equipment_means))
    group_std = float(np.std(equipment_means))

    # Set deviations and rank
    for tool in tool_stats:
        tool.deviation_from_group_mean = round(tool.mean_efficiency_pct - group_mean, 2)

    tool_stats.sort(key=lambda t: t.mean_efficiency_pct, reverse=True)
    for rank, tool in enumerate(tool_stats, start=1):
        tool.rank_in_group = rank

    total_shots = sum(t.shot_count for t in tool_stats)

    return ApprovedCTGroup(
        approved_ct=approved_ct,
        part_ids=part_ids,
        part_names=part_names,
        equipment_count=len(tool_stats),
        total_shots=total_shots,
        group_mean_efficiency=round(group_mean, 2),
        group_std_efficiency=round(group_std, 2),
        tools=tool_stats,
    )


# ==================== Batch Analysis ==================== #


def compare_tools_by_approved_ct(
    df: pd.DataFrame,
    tolerance: float = APPROVED_CT_TOLERANCE,
) -> List[ApprovedCTGroup]:
    """Run tool comparison across all approved CT groups.

    Args:
        df: Full DataFrame with efficiency_pct, CT, APPROVED_CT, tool_id
        tolerance: CT grouping tolerance in seconds

    Returns:
        List of ApprovedCTGroup results, sorted by equipment count desc
    """
    logger.info("Comparing tool performance within approved CT groups...")

    groups = build_approved_ct_groups(df, tolerance)

    results = []
    for ct_val, group_df in groups.items():
        group_result = analyze_group(ct_val, group_df)
        if group_result is not None:
            results.append(group_result)

    # Sort by number of equipment (most interesting groups first)
    results.sort(key=lambda g: g.equipment_count, reverse=True)

    logger.info(
        "Tool comparison complete: %d groups, %d total equipment entries",
        len(results),
        sum(g.equipment_count for g in results),
    )

    return results
