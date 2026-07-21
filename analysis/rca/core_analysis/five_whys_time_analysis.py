"""
Time-based Five Whys analysis functions for day-of-week root cause investigation.
This module contains standalone functions that check for specific issue patterns
and generate the five successive "why" explanations, root causes, and recommendations.
Each function accepts a metrics dictionary and returns strings or lists.
"""

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
SHIFT_CT_RANGE_THRESHOLD = 5
EQUIPMENT_CT_RANGE_THRESHOLD = 10
CT_VARIANCE_HIGH_THRESHOLD = 50
AVG_DOWNTIME_HIGH_THRESHOLD = 30
SHIFT_VARIANCE_TRAINING_THRESHOLD = 3
SHIFT_VARIANCE_ROOT_THRESHOLD = 5
MAX_RECOMMENDATIONS = 6

JOIN_SEPARATOR_AND = " and "


# ---------------------------------------------------------------------------
# Issue checkers (Why 1 helpers)
# ---------------------------------------------------------------------------


def check_ct_issue(metrics: Dict[str, Any]) -> Optional[str]:
    """Check whether cycle time is higher on the target day."""
    if "avg_ct_day" in metrics and "avg_ct_other" in metrics:
        ct_diff = metrics["avg_ct_day"] - metrics["avg_ct_other"]
        if ct_diff > 0:
            return "cycle time is %.1fs higher" % ct_diff
    return None


def check_ct_issues_count(metrics: Dict[str, Any]) -> Optional[str]:
    """Check whether CT issue count is higher on the target day."""
    if "ct_issues_day" in metrics and "ct_issues_other" in metrics:
        if metrics["ct_issues_day"] > metrics["ct_issues_other"]:
            return "has %d CT issues vs %d on other days" % (
                metrics["ct_issues_day"],
                metrics["ct_issues_other"],
            )
    return None


def check_efficiency_issue(metrics: Dict[str, Any]) -> Optional[str]:
    """Check whether efficiency is lower on the target day."""
    if "avg_efficiency_day" in metrics and "avg_efficiency_other" in metrics:
        eff_diff = metrics["avg_efficiency_other"] - metrics["avg_efficiency_day"]
        if eff_diff > 0:
            return "efficiency is %.1f%% lower" % eff_diff
    return None


def check_scrap_rate_issue(metrics: Dict[str, Any]) -> Optional[str]:
    """Check whether scrap rate is higher on the target day."""
    if "scrap_rate_day" in metrics and "scrap_rate_other" in metrics:
        if metrics["scrap_rate_day"] > metrics["scrap_rate_other"]:
            return "scrap rate is %.1f%% vs %.1f%%" % (
                metrics["scrap_rate_day"],
                metrics["scrap_rate_other"],
            )
    return None


# ---------------------------------------------------------------------------
# Why generators
# ---------------------------------------------------------------------------


def generate_why1_time(day_name: str, metrics: Dict[str, Any]) -> str:
    """Generate Why 1 based on actual data patterns for a specific day."""
    issues: List[str] = []

    ct_issue = check_ct_issue(metrics)
    if ct_issue:
        issues.append(ct_issue)

    ct_count = check_ct_issues_count(metrics)
    if ct_count:
        issues.append(ct_count)

    eff_issue = check_efficiency_issue(metrics)
    if eff_issue:
        issues.append(eff_issue)

    scrap_issue = check_scrap_rate_issue(metrics)
    if scrap_issue:
        issues.append(scrap_issue)

    if issues:
        return "%s %s" % (day_name, ", ".join(issues))
    return "%s shows performance variations compared to other days" % day_name


def generate_why2_time(metrics: Dict[str, Any]) -> str:
    """Generate Why 2 based on shift, hour, and equipment operational factors."""
    factors: List[str] = []

    if "shift_analysis" in metrics:
        worst_shift = metrics["shift_analysis"]["CT"]["mean"].idxmax()
        worst_shift_ct = metrics["shift_analysis"]["CT"]["mean"].max()
        factors.append(
            "%s shift has highest CT (%.1fs)" % (worst_shift, worst_shift_ct)
        )

    if "hour_analysis" in metrics:
        worst_hour = metrics["hour_analysis"]["CT"]["mean"].idxmax()
        worst_hour_ct = metrics["hour_analysis"]["CT"]["mean"].max()
        factors.append("hour %s shows peak CT (%.1fs)" % (worst_hour, worst_hour_ct))

    if "equipment_analysis" in metrics:
        worst_equip = metrics["equipment_analysis"]["CT"]["mean"].idxmax()
        worst_equip_ct = metrics["equipment_analysis"]["CT"]["mean"].max()
        factors.append(
            "equipment %s has highest CT (%.1fs)" % (worst_equip, worst_equip_ct)
        )

    if factors:
        return "Specific operational factors: %s" % ", ".join(factors)
    return "Operational procedures and staffing patterns differ on this day"


def generate_why3_time(metrics: Dict[str, Any]) -> str:
    """Generate Why 3 based on underlying operational issues."""
    issues: List[str] = []

    if "ct_variance_day" in metrics and "ct_variance_other" in metrics:
        if metrics["ct_variance_day"] > metrics["ct_variance_other"] * 1.5:
            issues.append("high cycle time variability")

    if "avg_downtime_day" in metrics and "avg_downtime_other" in metrics:
        if metrics["avg_downtime_day"] > metrics["avg_downtime_other"]:
            issues.append("increased downtime incidents")

    if "scrap_rate_day" in metrics and "scrap_rate_other" in metrics:
        if metrics["scrap_rate_day"] > metrics["scrap_rate_other"]:
            issues.append("higher scrap rates")

    if issues:
        return "These factors indicate: %s" % ", ".join(issues)
    return "Staffing, training, or operational procedures differ on this day"


def generate_why4_time(metrics: Dict[str, Any]) -> str:
    """Generate Why 4 based on systematic shift and equipment issues."""
    systematic_issues: List[str] = []

    if "shift_analysis" in metrics:
        shift_ct_range = (
            metrics["shift_analysis"]["CT"]["mean"].max()
            - metrics["shift_analysis"]["CT"]["mean"].min()
        )
        if shift_ct_range > SHIFT_CT_RANGE_THRESHOLD:
            systematic_issues.append("inconsistent performance across shifts")

    if "equipment_analysis" in metrics:
        equipment_ct_range = (
            metrics["equipment_analysis"]["CT"]["mean"].max()
            - metrics["equipment_analysis"]["CT"]["mean"].min()
        )
        if equipment_ct_range > EQUIPMENT_CT_RANGE_THRESHOLD:
            systematic_issues.append("equipment-specific performance issues")

    if systematic_issues:
        return "Systematic issues: %s" % ", ".join(systematic_issues)
    return "Inconsistent standard operating procedures across shifts/days"


def generate_why5_time(metrics: Dict[str, Any]) -> str:
    """Generate Why 5 based on fundamental root causes."""
    fundamental: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        fundamental.append("lack of standardized training across shifts")

    if (
        "ct_variance_day" in metrics
        and metrics["ct_variance_day"] > CT_VARIANCE_HIGH_THRESHOLD
    ):
        fundamental.append("inconsistent operating procedures")

    if (
        "avg_downtime_day" in metrics
        and metrics["avg_downtime_day"] > AVG_DOWNTIME_HIGH_THRESHOLD
    ):
        fundamental.append("inadequate preventive maintenance")

    if fundamental:
        return "Fundamental causes: %s" % ", ".join(fundamental)
    return "Lack of standardized training and procedure documentation"


# ---------------------------------------------------------------------------
# Root cause and recommendations
# ---------------------------------------------------------------------------


def determine_root_cause_time(metrics: Dict[str, Any]) -> str:
    """Determine root cause string based on actual data patterns."""
    root_causes: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        shift_variance = metrics["shift_analysis"]["CT"]["mean"].std()
        if shift_variance > SHIFT_VARIANCE_TRAINING_THRESHOLD:
            root_causes.append("inconsistent training across shifts")

    if (
        "ct_variance_day" in metrics
        and metrics["ct_variance_day"] > CT_VARIANCE_HIGH_THRESHOLD
    ):
        root_causes.append("non-standardized operating procedures")

    if (
        "avg_downtime_day" in metrics
        and metrics["avg_downtime_day"] > AVG_DOWNTIME_HIGH_THRESHOLD
    ):
        root_causes.append("inadequate preventive maintenance schedule")

    if "equipment_analysis" in metrics:
        equipment_variance = metrics["equipment_analysis"]["CT"]["mean"].std()
        if equipment_variance > SHIFT_VARIANCE_ROOT_THRESHOLD:
            root_causes.append("equipment-specific operational issues")

    if root_causes:
        return "Inconsistent operational procedures and training: %s" % ", ".join(
            root_causes
        )
    return "Inconsistent operational procedures and training across shifts"


def generate_recommendations_time(metrics: Dict[str, Any]) -> List[str]:
    """Generate data-driven recommendations based on actual patterns."""
    recommendations: List[str] = []

    if "shift_analysis" in metrics and len(metrics["shift_analysis"]) > 1:
        shift_variance = metrics["shift_analysis"]["CT"]["mean"].std()
        if shift_variance > SHIFT_VARIANCE_TRAINING_THRESHOLD:
            recommendations.append("Standardize training programs across all shifts")
            recommendations.append("Implement shift-specific performance coaching")

    if (
        "ct_variance_day" in metrics
        and metrics["ct_variance_day"] > CT_VARIANCE_HIGH_THRESHOLD
    ):
        recommendations.append("Standardize operating procedures for this day")
        recommendations.append("Create detailed work instructions for peak hours")

    if (
        "avg_downtime_day" in metrics
        and metrics["avg_downtime_day"] > AVG_DOWNTIME_HIGH_THRESHOLD
    ):
        recommendations.append("Implement preventive maintenance before this day")
        recommendations.append("Schedule equipment checks for high-usage periods")

    if "equipment_analysis" in metrics:
        worst_equip = metrics["equipment_analysis"]["CT"]["mean"].idxmax()
        recommendations.append(
            "Focus maintenance efforts on equipment %s" % worst_equip
        )

    recommendations.append("Implement real-time monitoring for this day")
    recommendations.append("Create daily performance review meetings")

    return recommendations[:MAX_RECOMMENDATIONS]
