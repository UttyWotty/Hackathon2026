"""
Duration Efficiency Result Serializers.

This module provides functions to convert analysis dataclass results into
dictionaries for JSON serialization and CSV-friendly string formatting.
"""

import logging
import os
from typing import Dict, List

import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)


# ==================== Supplier Benchmarks ==================== #


def benchmarks_to_dict(benchmarks: List) -> List[Dict]:
    """Convert SupplierBenchmark list to dictionary list for JSON serialization.

    Args:
        benchmarks: List of SupplierBenchmark objects

    Returns:
        List[Dict]: List of benchmarks as dictionaries
    """
    return [
        {
            "vendor_name": b.vendor_name,
            "performance_rank": b.performance_rank,
            "efficiency_score": round(b.mean_normalized_efficiency, 4),
            "consistency_score": round(b.tool_consistency_score, 2),
            "total_tools": b.total_tools,
            "tier_classification": b.tier_classification,
            "adjusted_score": round(b.adjusted_score, 4),
        }
        for b in benchmarks
    ]


# ==================== Operator Benchmarks ==================== #


def operator_benchmarks_to_dict(benchmarks: List) -> List[Dict]:
    """Convert OperatorBenchmark list to dictionary list for JSON serialization.

    Args:
        benchmarks: List of OperatorBenchmark objects

    Returns:
        List[Dict]: Serializable benchmark data
    """
    return [
        {
            "machine_id": b.machine_id,
            "process_type": b.process_type,
            "vendor_name": b.vendor_name,
            "session_count": b.session_count,
            "mean_efficiency_pct": b.mean_efficiency_pct,
            "within_session_consistency": b.within_session_consistency,
            "cross_session_consistency": b.cross_session_consistency,
            "warmup_impact_pct": b.warmup_impact_pct,
            "performance_rank": b.performance_rank,
            "tier_classification": b.tier_classification,
            "adjusted_score": round(b.adjusted_score, 4),
        }
        for b in benchmarks
    ]


# ==================== Shift Patterns ==================== #


def shift_patterns_to_dict(patterns: List) -> List[Dict]:
    """Convert OperatorShiftPattern list to dictionary list for JSON serialization.

    Args:
        patterns: List of OperatorShiftPattern objects

    Returns:
        List[Dict]: Serializable shift pattern data
    """
    return [
        {
            "machine_id": p.machine_id,
            "process_type": p.process_type,
            "total_sessions": p.total_sessions,
            "avg_session_duration_hours": p.avg_session_duration_hours,
            "avg_break_duration_hours": p.avg_break_duration_hours,
            "production_end_count": p.production_end_count,
            "has_planned_downtime": p.has_planned_downtime,
            "avg_warmup_penalty_pct": p.avg_warmup_penalty_pct,
            "shots_per_session": p.shots_per_session,
            "break_schedule": p.break_schedule,
        }
        for p in patterns
    ]


def format_break_schedule(schedule: List[Dict]) -> str:
    """Format break schedule list into a readable CSV-friendly string.

    Args:
        schedule: List of break cluster dicts

    Returns:
        Semicolon-separated summary string
    """
    if not schedule:
        return "None detected"
    parts = []
    for entry in schedule:
        parts.append(
            f"{entry['label']} @ {entry['avg_time']} "
            f"(~{entry['avg_duration_hours']}h, {entry['frequency_pct']}% of sessions)"
        )
    return "; ".join(parts)


# ==================== Shift Performance ==================== #


def shift_analyses_to_dict(analyses: List) -> List[Dict]:
    """Convert EquipmentShiftAnalysis list to dictionary list.

    Args:
        analyses: List of EquipmentShiftAnalysis objects

    Returns:
        List[Dict]: Serializable shift analysis data
    """
    results = []
    for a in analyses:
        entry = {
            "machine_id": a.machine_id,
            "process_type": a.process_type,
            "vendor_name": a.vendor_name,
            "overall_daily_std": a.overall_daily_std,
            "operator_impact": a.operator_impact,
            "best_day": a.best_day,
            "worst_day": a.worst_day,
            "shift_summaries": [
                {
                    "shift_label": s.shift_label,
                    "total_instances": s.total_instances,
                    "total_shots": s.total_shots,
                    "mean_of_daily_means": s.mean_of_daily_means,
                    "std_of_daily_means": s.std_of_daily_means,
                    "min_daily_mean": s.min_daily_mean,
                    "max_daily_mean": s.max_daily_mean,
                    "mean_transition_penalty": s.mean_transition_penalty,
                }
                for s in a.shift_summaries
            ],
        }
        if a.variance is not None:
            entry["variance"] = {
                "within_day_std": a.variance.within_day_std,
                "across_day_std": a.variance.across_day_std,
                "operator_ratio": a.variance.operator_ratio,
                "days_with_all_shifts": a.variance.days_with_all_shifts,
                "conclusion": a.variance.conclusion,
            }
        results.append(entry)
    return results


def save_shift_performance_to_csv(
    analyses: List,
    output_dir: str,
    timestamp: str,
) -> str:
    """Save two CSVs: daily detail and per-equipment variance summary.

    Args:
        analyses: List of EquipmentShiftAnalysis objects
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved summary CSV file
    """
    # Detail CSV: one row per equipment+date+shift
    detail_rows = []
    for a in analyses:
        v = a.variance
        for inst in a.daily_instances:
            detail_rows.append(
                {
                    "Machine_Id": a.machine_id,
                    "Tooling_Type": a.process_type,
                    "Vendor_Name": a.vendor_name,
                    "Date": inst.date,
                    "Shift": inst.shift_label,
                    "Shot_Count": inst.shot_count,
                    "Mean_Efficiency_Pct": inst.mean_efficiency_pct,
                    "Median_Efficiency_Pct": inst.median_efficiency_pct,
                    "Std_Efficiency_Pct": inst.std_efficiency_pct,
                    "Mean_CT_Seconds": inst.mean_duration,
                    "First_20_Efficiency_Pct": inst.first_20_efficiency_pct,
                    "Steady_Efficiency_Pct": inst.steady_efficiency_pct,
                }
            )

    detail_df = pd.DataFrame(detail_rows)
    detail_path = os.path.join(output_dir, f"shift_detail_{timestamp}.csv")
    detail_df.to_csv(detail_path, index=False)
    logger.info("Shift detail CSV saved to %s (%d rows)", detail_path, len(detail_rows))

    # Summary CSV: one row per equipment with variance verdict
    summary_rows = []
    for a in analyses:
        v = a.variance
        summary_rows.append(
            {
                "Machine_Id": a.machine_id,
                "Tooling_Type": a.process_type,
                "Vendor_Name": a.vendor_name,
                "Within_Day_Std": v.within_day_std if v else "",
                "Across_Day_Std": v.across_day_std if v else "",
                "Operator_Ratio": v.operator_ratio if v else "",
                "Days_With_All_Shifts": v.days_with_all_shifts if v else "",
                "Operator_Impact": a.operator_impact,
                "Conclusion": v.conclusion if v else "Insufficient multi-shift days",
                "Overall_Daily_Std": a.overall_daily_std,
                "Best_Day": a.best_day,
                "Worst_Day": a.worst_day,
            }
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_path = os.path.join(output_dir, f"operator_vs_machine_{timestamp}.csv")
    summary_df.to_csv(summary_path, index=False)
    logger.info("Operator vs machine CSV saved to %s", summary_path)

    return summary_path


# ==================== Tool Comparison ==================== #


def tool_comparison_to_dict(groups: List) -> List[Dict]:
    """Convert ApprovedCTGroup list to dictionary list.

    Args:
        groups: List of ApprovedCTGroup objects

    Returns:
        List[Dict]: Serializable comparison data
    """
    return [
        {
            "target_duration": g.target_duration,
            "product_ids": g.product_ids,
            "product_names": g.product_names,
            "equipment_count": g.equipment_count,
            "total_shots": g.total_shots,
            "group_mean_efficiency": g.group_mean_efficiency,
            "group_std_efficiency": g.group_std_efficiency,
            "tools": [
                {
                    "machine_id": t.machine_id,
                    "process_type": t.process_type,
                    "vendor_name": t.vendor_name,
                    "shot_count": t.shot_count,
                    "mean_efficiency_pct": t.mean_efficiency_pct,
                    "median_efficiency_pct": t.median_efficiency_pct,
                    "std_efficiency_pct": t.std_efficiency_pct,
                    "mean_duration": t.mean_duration,
                    "rank_in_group": t.rank_in_group,
                    "deviation_from_group_mean": t.deviation_from_group_mean,
                }
                for t in g.tools
            ],
        }
        for g in groups
    ]


def save_tool_comparison_to_csv(
    groups: List,
    output_dir: str,
    timestamp: str,
) -> str:
    """Save tool comparison to CSV -- one row per equipment per group.

    Args:
        groups: List of ApprovedCTGroup objects
        output_dir: Output directory
        timestamp: Timestamp string for filename

    Returns:
        str: Path to saved CSV file
    """
    rows = []
    for g in groups:
        for t in g.tools:
            rows.append(
                {
                    "Target_Duration": g.target_duration,
                    "Part_IDs": "; ".join(g.product_ids[:5]),
                    "Part_Names": "; ".join(g.product_names[:5]),
                    "Group_Equipment_Count": g.equipment_count,
                    "Group_Mean_Efficiency": g.group_mean_efficiency,
                    "Group_Std_Efficiency": g.group_std_efficiency,
                    "Machine_Id": t.machine_id,
                    "Tooling_Type": t.process_type,
                    "Vendor_Name": t.vendor_name,
                    "Shot_Count": t.shot_count,
                    "Mean_Efficiency_Pct": t.mean_efficiency_pct,
                    "Median_Efficiency_Pct": t.median_efficiency_pct,
                    "Std_Efficiency_Pct": t.std_efficiency_pct,
                    "Mean_CT_Seconds": t.mean_duration,
                    "Rank_In_Group": t.rank_in_group,
                    "Deviation_From_Group_Mean": t.deviation_from_group_mean,
                }
            )

    df = pd.DataFrame(rows)
    csv_path = os.path.join(output_dir, f"tool_comparison_{timestamp}.csv")
    df.to_csv(csv_path, index=False)
    logger.info("Tool comparison CSV saved to %s (%d rows)", csv_path, len(rows))

    return csv_path


# ==================== Windowed Tool Comparison ==================== #


def save_windowed_comparison_to_csv(
    groups: List,
    output_dir: str,
    timestamp: str,
) -> str:
    """Save two CSVs: monthly detail and per-equipment trend summary.

    Args:
        groups: List of WindowedGroupResult objects
        output_dir: Output directory
        timestamp: Timestamp string

    Returns:
        str: Path to trend summary CSV
    """
    # Detail: one row per equipment per month per group
    detail_rows = []
    for g in groups:
        for s in g.window_stats:
            detail_rows.append(
                {
                    "Target_Duration": g.target_duration,
                    "Part_Names": "; ".join(g.product_names[:3]),
                    "Window": s.window,
                    "Machine_Id": s.machine_id,
                    "Tooling_Type": s.process_type,
                    "Shot_Count": s.shot_count,
                    "Mean_Efficiency_Pct": s.mean_efficiency_pct,
                    "Std_Efficiency_Pct": s.std_efficiency_pct,
                    "Mean_CT_Seconds": s.mean_duration,
                    "Rank_In_Window": s.rank_in_window,
                    "Deviation_From_Window_Mean": s.deviation_from_window_mean,
                }
            )

    detail_df = pd.DataFrame(detail_rows)
    detail_path = os.path.join(output_dir, f"tool_monthly_detail_{timestamp}.csv")
    detail_df.to_csv(detail_path, index=False)
    logger.info(
        "Monthly detail CSV saved to %s (%d rows)", detail_path, len(detail_rows)
    )

    # Trend summary: one row per equipment per group
    trend_rows = []
    for g in groups:
        for t in g.trend_summaries:
            trend_rows.append(
                {
                    "Target_Duration": g.target_duration,
                    "Part_Names": "; ".join(g.product_names[:3]),
                    "Group_Equipment_Count": g.equipment_count,
                    "Rankings_Stable": g.rankings_stable,
                    "Machine_Id": t.machine_id,
                    "Tooling_Type": t.process_type,
                    "Windows_Present": t.windows_present,
                    "Mean_Rank": t.mean_rank,
                    "Rank_Std": t.rank_std,
                    "Efficiency_Trend_Per_Month": t.efficiency_trend,
                    "Best_Window": t.best_window,
                    "Best_Efficiency": t.best_efficiency,
                    "Worst_Window": t.worst_window,
                    "Worst_Efficiency": t.worst_efficiency,
                }
            )

    trend_df = pd.DataFrame(trend_rows)
    trend_path = os.path.join(output_dir, f"tool_trend_summary_{timestamp}.csv")
    trend_df.to_csv(trend_path, index=False)
    logger.info("Trend summary CSV saved to %s", trend_path)

    return trend_path


# ==================== Staleness Detection ==================== #


def save_staleness_report_to_csv(
    results: List,
    output_dir: str,
    timestamp: str,
) -> str:
    """Save staleness detection results to CSV.

    Args:
        results: List of StalenessResult objects
        output_dir: Output directory
        timestamp: Timestamp string

    Returns:
        str: Path to saved CSV file
    """
    rows = []
    for r in results:
        rows.append(
            {
                "Target_Duration": r.target_duration,
                "Part_Names": "; ".join(r.product_names[:3]),
                "Months_Analyzed": r.months_analyzed,
                "Severity": r.severity,
                "Is_Stale": r.is_stale,
                "Trend_Per_Month": r.trend_per_month,
                "Earliest_Efficiency": r.earliest_efficiency,
                "Latest_Efficiency": r.latest_efficiency,
                "Total_Drift": r.total_drift,
                "Current_Target_Duration": r.target_duration,
                "Latest_Actual_Mean_CT": (
                    r.monthly_snapshots[-1].mean_duration if r.monthly_snapshots else ""
                ),
                "Suggested_CT": r.suggested_duration,
                "Reasoning": r.reasoning,
            }
        )

    df = pd.DataFrame(rows)
    csv_path = os.path.join(output_dir, f"target_duration_staleness_{timestamp}.csv")
    df.to_csv(csv_path, index=False)
    logger.info("Staleness report CSV saved to %s", csv_path)

    return csv_path


# ==================== Supplier Shift Detection ==================== #


def save_supplier_shifts_to_csv(
    supplier_shifts: Dict,
    output_dir: str,
    timestamp: str,
) -> str:
    """Save per-supplier detected shift schedules to CSV.

    Args:
        supplier_shifts: Dict mapping supplier name to DetectedShifts
        output_dir: Output directory
        timestamp: Timestamp string

    Returns:
        str: Path to saved CSV file
    """
    rows = []
    for vendor_name, shifts in supplier_shifts.items():
        rows.append(
            {
                "Vendor_Name": vendor_name,
                "Num_Shifts": shifts.num_shifts,
                "Boundaries": " / ".join(f"{b:02d}:00" for b in shifts.boundaries),
                "Labels": " | ".join(shifts.labels),
                "Confidence": shifts.confidence,
                "Night_Activity": shifts.night_activity,
                "Method": shifts.method,
                "Dip_Hours": ", ".join(str(h) for h in shifts.dip_hours),
            }
        )

    result_df = pd.DataFrame(rows)
    csv_path = os.path.join(output_dir, f"supplier_shifts_{timestamp}.csv")
    result_df.to_csv(csv_path, index=False)
    logger.info("Supplier shifts CSV saved to %s", csv_path)

    return csv_path
