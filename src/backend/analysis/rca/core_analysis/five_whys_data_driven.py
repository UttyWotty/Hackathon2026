"""
Data-driven Five Whys analysis functions for general target comparisons.
This module generates the five successive "why" explanations, root causes,
and recommendations using comprehensive metrics calculated from target vs.
comparison data. It also provides the orchestrating generate_data_driven_analysis
function that assembles a complete analysis dictionary.
"""

import logging
from typing import Any, Dict, List

import pandas as pd  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
JOIN_SEPARATOR_AND = " and "
HOUR_VARIANCE_THRESHOLD = 5
SHIFT_VARIANCE_THRESHOLD = 3
SHIFT_VARIANCE_HIGH_THRESHOLD = 5
EQUIPMENT_VARIANCE_THRESHOLD = 10
CT_STD_THRESHOLD = 10
EFFICIENCY_LOW_THRESHOLD = 85
MAX_RECOMMENDATIONS = 6
PERCENT_MULTIPLIER = 100


# ---------------------------------------------------------------------------
# Comprehensive metrics (used by the data-driven analysis path)
# ---------------------------------------------------------------------------


def calculate_comprehensive_metrics(
    target_data: pd.DataFrame,
    comparison_data: pd.DataFrame,
    data_type: str,
) -> Dict[str, Any]:
    """
    Calculate comprehensive metrics for comparison analysis.

    Args:
        target_data: Data for the target (day/equipment).
        comparison_data: Data for comparison group.
        data_type: Type of analysis ('day' or 'equipment').

    Returns:
        Comprehensive metrics dictionary.
    """
    metrics: Dict[str, Any] = {
        "target_count": len(target_data),
        "comparison_count": len(comparison_data),
    }
    _add_ct_comprehensive(metrics, target_data, comparison_data)
    _add_efficiency_comprehensive(metrics, target_data, comparison_data)
    _add_temperature_comprehensive(metrics, target_data, comparison_data)
    _add_groupby_analyses(metrics, target_data)
    _add_performance_indicators(metrics, target_data, comparison_data)
    logger.info("Calculated %d comprehensive metrics", len(metrics))
    return metrics


def _add_ct_comprehensive(
    metrics: Dict[str, Any],
    target: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    if "DURATION" not in target.columns:
        return
    metrics["target_duration_mean"] = target["DURATION"].mean()
    metrics["target_duration_std"] = target["DURATION"].std()
    metrics["comparison_ct_mean"] = comparison["DURATION"].mean()
    metrics["comparison_ct_std"] = comparison["DURATION"].std()
    if "CT_ISSUE_FLAG" in target.columns:
        metrics["target_duration_issues"] = target["CT_ISSUE_FLAG"].sum()
        metrics["comparison_ct_issues"] = comparison["CT_ISSUE_FLAG"].sum()
        metrics["target_issue_rate"] = (
            metrics["target_duration_issues"] / len(target)
        ) * PERCENT_MULTIPLIER
        metrics["comparison_issue_rate"] = (
            metrics["comparison_ct_issues"] / len(comparison)
        ) * PERCENT_MULTIPLIER


def _add_efficiency_comprehensive(
    metrics: Dict[str, Any],
    target: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    if "EFFICIENCY" not in target.columns:
        return
    metrics["target_efficiency_mean"] = target["EFFICIENCY"].mean()
    metrics["target_efficiency_std"] = target["EFFICIENCY"].std()
    metrics["comparison_efficiency_mean"] = comparison["EFFICIENCY"].mean()
    metrics["comparison_efficiency_std"] = comparison["EFFICIENCY"].std()


def _add_temperature_comprehensive(
    metrics: Dict[str, Any],
    target: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    if "TEMPERATURE" not in target.columns:
        return
    metrics["target_avg_temp"] = target["TEMPERATURE"].mean()
    metrics["comparison_avg_temp"] = comparison["TEMPERATURE"].mean()


def _build_agg_dict(data: pd.DataFrame) -> Dict[str, Any]:
    """Build a standard aggregation dict for groupby analyses."""
    agg: Dict[str, Any] = {"DURATION": ["mean", "std", "count"]}
    if "EFFICIENCY" in data.columns:
        agg["EFFICIENCY"] = "mean"
    if "CT_ISSUE_FLAG" in data.columns:
        agg["CT_ISSUE_FLAG"] = "sum"
    return agg


def _add_groupby_analyses(
    metrics: Dict[str, Any],
    target: pd.DataFrame,
) -> None:
    agg = _build_agg_dict(target)
    for col, key in [
        ("SHIFT", "shift_analysis"),
        ("HOUR", "hour_analysis"),
        ("MACHINE_ID", "equipment_analysis"),
        ("DAY_OF_WEEK", "day_analysis"),
    ]:
        if col in target.columns:
            metrics[key] = target.groupby(col).agg(agg).round(2)


def _add_performance_indicators(
    metrics: Dict[str, Any],
    target: pd.DataFrame,
    comparison: pd.DataFrame,
) -> None:
    if "DURATION" in target.columns:
        metrics["ct_variance_target"] = target["DURATION"].var()
        metrics["ct_variance_comparison"] = comparison["DURATION"].var()
        if metrics["target_duration_mean"] > metrics["comparison_ct_mean"]:
            metrics["duration_performance_gap"] = (
                metrics["target_duration_mean"] - metrics["comparison_ct_mean"]
            )
        else:
            metrics["duration_performance_gap"] = 0
    if "EFFICIENCY" in target.columns:
        if metrics["target_efficiency_mean"] < metrics["comparison_efficiency_mean"]:
            metrics["efficiency_gap"] = (
                metrics["comparison_efficiency_mean"]
                - metrics["target_efficiency_mean"]
            )
        else:
            metrics["efficiency_gap"] = 0


# ---------------------------------------------------------------------------
# Why generators
# ---------------------------------------------------------------------------


def generate_why1_data_driven(
    target_code: str,
    metrics: Dict[str, Any],
    data_type: str,
) -> str:
    """Generate Why 1 based on process-duration difference for the target."""
    label = (
        "Day"
        if data_type == "day"
        else ("Equipment" if data_type == "equipment" else target_code)
    )

    if "target_duration_mean" not in metrics or "comparison_ct_mean" not in metrics:
        return "%s shows performance differences compared to others" % target_code

    if metrics["target_duration_mean"] > metrics["comparison_ct_mean"]:
        ct_diff = metrics["target_duration_mean"] - metrics["comparison_ct_mean"]
        return "%s %s has %.1fs higher duration than other %ss" % (
            label,
            target_code,
            ct_diff,
            data_type,
        )

    ct_diff = metrics["comparison_ct_mean"] - metrics["target_duration_mean"]
    return "%s %s has %.1fs lower duration than other %ss" % (
        label,
        target_code,
        ct_diff,
        data_type,
    )


def generate_why2_data_driven(
    target_code: str,
    metrics: Dict[str, Any],
) -> str:
    """Generate Why 2 based on shift, hour, and efficiency contributing factors."""
    factors: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        worst_shift = metrics["shift_analysis"]["DURATION"]["mean"].idxmax()
        best_shift = metrics["shift_analysis"]["DURATION"]["mean"].idxmin()
        shift_diff = (
            metrics["shift_analysis"]["DURATION"]["mean"].max()
            - metrics["shift_analysis"]["DURATION"]["mean"].min()
        )
        factors.append(
            "%s shift has %.1fs higher duration than %s shift"
            % (worst_shift, shift_diff, best_shift)
        )

    if "hour_analysis" in metrics and len(metrics["hour_analysis"]) > 1:
        worst_hour = metrics["hour_analysis"]["DURATION"]["mean"].idxmax()
        best_hour = metrics["hour_analysis"]["DURATION"]["mean"].idxmin()
        hour_diff = (
            metrics["hour_analysis"]["DURATION"]["mean"].max()
            - metrics["hour_analysis"]["DURATION"]["mean"].min()
        )
        factors.append(
            "Hour %s has %.1fs higher duration than hour %s"
            % (worst_hour, hour_diff, best_hour)
        )

    if (
        "target_efficiency_mean" in metrics
        and "comparison_efficiency_mean" in metrics
        and metrics["target_efficiency_mean"] < metrics["comparison_efficiency_mean"]
    ):
        eff_diff = (
            metrics["comparison_efficiency_mean"] - metrics["target_efficiency_mean"]
        )
        factors.append("Efficiency is %.1f%% lower than average" % eff_diff)

    if factors:
        return JOIN_SEPARATOR_AND.join(factors)
    return "Multiple operational factors contribute to %s performance" % target_code


def generate_why3_data_driven(
    target_code: str,
    metrics: Dict[str, Any],
) -> str:
    """Generate Why 3 based on underlying hourly, shift, and equipment patterns."""
    patterns: List[str] = []

    if "hour_analysis" in metrics:
        hour_variance = metrics["hour_analysis"]["DURATION"]["mean"].std()
        if hour_variance > HOUR_VARIANCE_THRESHOLD:
            patterns.append("Significant hourly performance variations exist")

    if "shift_analysis" in metrics:
        shift_variance = metrics["shift_analysis"]["DURATION"]["mean"].std()
        if shift_variance > SHIFT_VARIANCE_THRESHOLD:
            patterns.append("Shift-to-shift performance inconsistencies")

    if "equipment_analysis" in metrics:
        equipment_variance = metrics["equipment_analysis"]["DURATION"]["mean"].std()
        if equipment_variance > EQUIPMENT_VARIANCE_THRESHOLD:
            patterns.append("Equipment performance varies significantly")

    if patterns:
        return JOIN_SEPARATOR_AND.join(patterns)
    return "Operational patterns affect %s performance" % target_code


def generate_why4_data_driven(
    target_code: str,
    metrics: Dict[str, Any],
) -> str:
    """Generate Why 4 based on training, procedure, and maintenance issues."""
    systematic_issues: List[str] = []

    if (
        "shift_analysis" in metrics
        and len(metrics["shift_analysis"]) > 1
        and metrics["shift_analysis"]["DURATION"]["mean"].std()
        > SHIFT_VARIANCE_HIGH_THRESHOLD
    ):
        systematic_issues.append("Inconsistent training across shifts")

    if (
        "target_duration_std" in metrics
        and metrics["target_duration_std"] > CT_STD_THRESHOLD
    ):
        systematic_issues.append("Non-standardized operating procedures")

    if (
        "equipment_analysis" in metrics
        and metrics["equipment_analysis"]["DURATION"]["mean"].idxmax() == target_code
    ):
        systematic_issues.append("Inadequate preventive maintenance")

    if systematic_issues:
        return JOIN_SEPARATOR_AND.join(systematic_issues)
    return "Systematic operational issues affect %s" % target_code


def generate_why5_data_driven(
    target_code: str,
    metrics: Dict[str, Any],
    target_data: pd.DataFrame,
    data_type: str,
) -> str:
    """Generate Why 5 based on fundamental root causes."""
    root_causes: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        shift_variance = metrics["shift_analysis"]["DURATION"]["mean"].std()
        if shift_variance > SHIFT_VARIANCE_HIGH_THRESHOLD:
            root_causes.append(
                "Lack of standardized training and procedure documentation"
            )

    if (
        "target_duration_std" in metrics
        and metrics["target_duration_std"] > CT_STD_THRESHOLD
    ):
        root_causes.append("Absence of systematic approach to process optimization")

    if "equipment_analysis" in metrics:
        worst_equipment = metrics["equipment_analysis"]["DURATION"]["mean"].idxmax()
        if worst_equipment == target_code:
            root_causes.append(
                "Inadequate equipment management and maintenance protocols"
            )

    if root_causes:
        return JOIN_SEPARATOR_AND.join(root_causes)
    return "Fundamental operational management issues affect %s" % target_code


# ---------------------------------------------------------------------------
# Root cause and recommendations
# ---------------------------------------------------------------------------


def determine_root_cause_data_driven(
    metrics: Dict[str, Any],
    target_data: pd.DataFrame,
    data_type: str,
) -> str:
    """Determine the root cause string from comprehensive metrics."""
    root_causes: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        shift_variance = metrics["shift_analysis"]["DURATION"]["mean"].std()
        if shift_variance > SHIFT_VARIANCE_HIGH_THRESHOLD:
            root_causes.append("inconsistent training across shifts")

    if (
        "target_duration_std" in metrics
        and metrics["target_duration_std"] > CT_STD_THRESHOLD
    ):
        root_causes.append("non-standardized operating procedures")

    if "equipment_analysis" in metrics:
        worst_equipment = metrics["equipment_analysis"]["DURATION"]["mean"].idxmax()
        root_causes.append("equipment %s performance issues" % worst_equipment)

    if (
        "target_efficiency_mean" in metrics
        and metrics["target_efficiency_mean"] < EFFICIENCY_LOW_THRESHOLD
    ):
        root_causes.append("low operational efficiency")

    if root_causes:
        return JOIN_SEPARATOR_AND.join(root_causes)
    return "operational performance optimization needed"


def generate_recommendations_data_driven(
    metrics: Dict[str, Any],
    target_data: pd.DataFrame,
    data_type: str,
) -> List[str]:
    """Generate data-driven recommendations based on actual patterns."""
    recommendations: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        shift_variance = metrics["shift_analysis"]["DURATION"]["mean"].std()
        if shift_variance > SHIFT_VARIANCE_THRESHOLD:
            recommendations.append("Standardize training programs across all shifts")
            recommendations.append("Implement shift-specific performance coaching")

    if (
        "target_duration_std" in metrics
        and metrics["target_duration_std"] > CT_STD_THRESHOLD
    ):
        recommendations.append("Standardize operating procedures")
        recommendations.append("Create detailed work instructions")

    if "equipment_analysis" in metrics:
        worst_equipment = metrics["equipment_analysis"]["DURATION"]["mean"].idxmax()
        recommendations.append(
            "Focus maintenance efforts on equipment %s" % worst_equipment
        )

    if (
        "target_efficiency_mean" in metrics
        and metrics["target_efficiency_mean"] < EFFICIENCY_LOW_THRESHOLD
    ):
        recommendations.append("Implement efficiency improvement programs")
        recommendations.append("Optimize process parameters")

    recommendations.append("Implement real-time monitoring")
    recommendations.append("Create daily performance review meetings")

    return recommendations[:MAX_RECOMMENDATIONS]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


def generate_data_driven_analysis(
    target_name: str,
    target_code: str,
    metrics: Dict[str, Any],
    target_data: pd.DataFrame,
    data_type: str,
) -> Dict[str, Any]:
    """
    Assemble a complete data-driven Five Whys analysis dictionary.

    Args:
        target_name: Display name of the target.
        target_code: Code identifier (day name or equipment code).
        metrics: Comprehensive metrics dictionary.
        target_data: DataFrame filtered to the target.
        data_type: 'day' or 'equipment'.

    Returns:
        Complete Five Whys analysis with whys, root_cause, and recommendations.
    """
    logger.info("Generating data-driven analysis for %s", target_name)

    analysis: Dict[str, Any] = {
        "target": target_name,
        "type": data_type.capitalize(),
        "whys": [],
        "root_cause": "",
        "supporting_data": metrics,
        "recommendations": [],
    }

    analysis["whys"].append(generate_why1_data_driven(target_code, metrics, data_type))
    analysis["whys"].append(generate_why2_data_driven(target_code, metrics))
    analysis["whys"].append(generate_why3_data_driven(target_code, metrics))
    analysis["whys"].append(generate_why4_data_driven(target_code, metrics))
    analysis["whys"].append(
        generate_why5_data_driven(target_code, metrics, target_data, data_type)
    )

    analysis["root_cause"] = determine_root_cause_data_driven(
        metrics, target_data, data_type
    )
    analysis["recommendations"] = generate_recommendations_data_driven(
        metrics, target_data, data_type
    )

    logger.info(
        "Generated data-driven analysis with %d recommendations",
        len(analysis["recommendations"]),
    )
    return analysis
