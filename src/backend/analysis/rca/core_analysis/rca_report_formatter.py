"""
Report formatting and display functions for Root Cause Analysis results.
Provides pure functions that accept analysis data dicts and produce formatted
log output, summary dicts, and serialized JSON reports.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# -- Constants ----------------------------------------------------------------

IMPROVEMENT_FACTOR = 0.5
IMPROVEMENT_PERCENTAGE = 50
ESTIMATED_TIME_TO_IMPROVEMENT = "3 months"
DURATION_VARIABILITY_TARGET = "25% reduction"
EQUIPMENT_UPTIME_TARGET = "10% improvement"
SCRAP_RATE_TARGET = "30% reduction"
TOP_ACTIONS_DISPLAY_LIMIT = 5


# -- Five Whys Summarization --------------------------------------------------


def summarize_five_whys(five_whys_results: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize 5 Whys results into a compact overview dict.

    Args:
        five_whys_results: Raw five-whys action plans keyed by target name.

    Returns:
        Dict with total_targets, total_actions, high_priority_actions, and
        root_causes mapping.
    """
    summary: Dict[str, Any] = {
        "total_targets": len(five_whys_results),
        "total_actions": sum(
            len(plan.get("recommendations", []))
            for plan in five_whys_results.values()
            if isinstance(plan, dict)
        ),
        "high_priority_actions": sum(
            len(
                [
                    a
                    for a in plan.get("recommendations", [])
                    if isinstance(a, dict) and a.get("priority") == "High"
                ]
            )
            for plan in five_whys_results.values()
            if isinstance(plan, dict)
        ),
        "root_causes": {},
    }

    for target, plan in five_whys_results.items():
        if isinstance(plan, dict):
            summary["root_causes"][target] = plan.get("root_cause", "Unknown")
        else:
            summary["root_causes"][target] = str(plan)

    return summary


# -- Priority Actions ----------------------------------------------------------


def get_priority_actions(
    five_whys_results: Dict[str, Any],
) -> List[Dict[str, str]]:
    """
    Extract high-priority actions across all five-whys targets.

    Args:
        five_whys_results: Raw five-whys action plans keyed by target name.

    Returns:
        Sorted list of action dicts (target, action_id, description, timeline).
    """
    priority_actions: List[Dict[str, str]] = []

    for target, plan in five_whys_results.items():
        if not isinstance(plan, dict):
            continue

        recommendations = plan.get("recommendations", [])
        high_priority = [
            a
            for a in recommendations
            if isinstance(a, dict) and a.get("priority") == "High"
        ]
        for action in high_priority:
            priority_actions.append(
                {
                    "target": target,
                    "action_id": action.get("id", "N/A"),
                    "description": action.get(
                        "description", action.get("recommendation", "N/A")
                    ),
                    "timeline": action.get("timeline", "Unknown"),
                }
            )

    return sorted(priority_actions, key=lambda x: x.get("timeline", "ZZZ"))


# -- Expected Impact -----------------------------------------------------------


def calculate_expected_impact(
    pareto_results: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Calculate expected impact of recommended actions based on Pareto results.

    Args:
        pareto_results: Dict containing at least an 'issue_rate' key.

    Returns:
        Dict describing current rate, target rate, improvement percentage,
        estimated timeline, and key metric targets.
    """
    current_rate: float = pareto_results.get("issue_rate", 0.0)
    return {
        "current_issue_rate": current_rate,
        "target_issue_rate": current_rate * IMPROVEMENT_FACTOR,
        "improvement_percentage": IMPROVEMENT_PERCENTAGE,
        "estimated_time_to_improvement": ESTIMATED_TIME_TO_IMPROVEMENT,
        "key_metrics": {
            "duration_variability": DURATION_VARIABILITY_TARGET,
            "equipment_uptime": EQUIPMENT_UPTIME_TARGET,
            "scrap_rate": SCRAP_RATE_TARGET,
        },
    }


# -- Report Printing -----------------------------------------------------------


def print_comprehensive_report(analysis_summary: Dict[str, Any]) -> None:
    """
    Log a formatted comprehensive report to the module logger.

    Replaces the former print-with-emoji approach with structured logger calls.
    Sections: executive summary, top issues, root causes, priority actions,
    expected impact, and action summary.

    Args:
        analysis_summary: Full analysis summary dict produced by
            generate_comprehensive_report on the pipeline.
    """
    pareto = analysis_summary.get("pareto_results", {})
    impact = analysis_summary.get("expected_impact", {})
    five_whys = analysis_summary.get("five_whys_results", {})
    data_summary = analysis_summary.get("data_summary", {})

    logger.info("COMPREHENSIVE ROOT CAUSE ANALYSIS REPORT")
    logger.info("=" * 80)

    _log_executive_summary(analysis_summary, data_summary, impact)
    _log_top_issues(pareto)
    _log_root_causes(five_whys)
    _log_priority_actions(analysis_summary.get("priority_actions", []))
    _log_expected_impact(impact)
    _log_action_summary(five_whys)


def _log_executive_summary(
    analysis_summary: Dict[str, Any],
    data_summary: Dict[str, Any],
    impact: Dict[str, Any],
) -> None:
    """Log the executive summary section."""
    logger.info("EXECUTIVE SUMMARY")
    logger.info("  Analysis Date: %s", analysis_summary.get("analysis_date", "N/A"))
    logger.info("  Total Shots Analyzed: %s", f"{data_summary.get('total_shots', 0):,}")
    logger.info("  Current Issue Rate: %.1f%%", impact.get("current_issue_rate", 0))
    logger.info("  Target Issue Rate: %.1f%%", impact.get("target_issue_rate", 0))
    logger.info("  Expected Improvement: %s%%", impact.get("improvement_percentage", 0))


def _log_top_issues(pareto: Dict[str, Any]) -> None:
    """Log the top-issues section from Pareto results."""
    logger.info("TOP ISSUES IDENTIFIED")
    top_equipment = pareto.get("top_equipment", [])
    if top_equipment:
        logger.info(
            "  Top Equipment Issue: %s (%.1f%%)",
            top_equipment[0].get("MACHINE_ID", "N/A"),
            top_equipment[0].get("Issue_Rate", 0),
        )
    top_parts = pareto.get("top_parts", [])
    if top_parts:
        logger.info(
            "  Top Part Issue: %s (%.1f%%)",
            top_parts[0].get("PRODUCT_NAME", "N/A"),
            top_parts[0].get("Issue_Rate", 0),
        )
    top_time = pareto.get("top_time_patterns", [])
    if top_time:
        logger.info(
            "  Top Time Pattern: %s (%.1f%%)",
            top_time[0].get("DAY_OF_WEEK", "N/A"),
            top_time[0].get("Issue_Rate", 0),
        )


def _log_root_causes(five_whys: Dict[str, Any]) -> None:
    """Log root causes from five-whys summary."""
    logger.info("ROOT CAUSES IDENTIFIED")
    for target, root_cause in five_whys.get("root_causes", {}).items():
        logger.info("  - %s: %s", target, root_cause)


def _log_priority_actions(priority_actions: List[Dict[str, str]]) -> None:
    """Log the top priority actions."""
    logger.info("HIGH-PRIORITY ACTIONS")
    for action in priority_actions[:TOP_ACTIONS_DISPLAY_LIMIT]:
        logger.info(
            "  - %s (%s): %s",
            action.get("action_id", "N/A"),
            action.get("timeline", "Unknown"),
            action.get("description", "N/A"),
        )


def _log_expected_impact(impact: Dict[str, Any]) -> None:
    """Log expected impact metrics."""
    logger.info("EXPECTED IMPACT")
    logger.info(
        "  - Issue Rate: %.1f%% -> %.1f%%",
        impact.get("current_issue_rate", 0),
        impact.get("target_issue_rate", 0),
    )
    key_metrics = impact.get("key_metrics", {})
    logger.info(
        "  - Duration Variability: %s",
        key_metrics.get("duration_variability", "N/A"),
    )
    logger.info(
        "  - Equipment Uptime: %s",
        key_metrics.get("equipment_uptime", "N/A"),
    )
    logger.info(
        "  - Time to Improvement: %s",
        impact.get("estimated_time_to_improvement", "N/A"),
    )


def _log_action_summary(five_whys: Dict[str, Any]) -> None:
    """Log the action count summary."""
    logger.info("ACTION SUMMARY")
    logger.info("  - Total Actions: %s", five_whys.get("total_actions", 0))
    logger.info("  - High Priority: %s", five_whys.get("high_priority_actions", 0))
    logger.info("  - Targets Analyzed: %s", five_whys.get("total_targets", 0))


# -- Report Persistence --------------------------------------------------------


def save_report(
    analysis_summary: Dict[str, Any],
    filename: Optional[str] = None,
) -> str:
    """
    Serialize the analysis summary to a JSON file.

    Handles datetime conversion for date_range fields. Returns the filename
    that was written.

    Args:
        analysis_summary: Full analysis summary dict.
        filename: Target path. If None, a timestamped default is generated.

    Returns:
        The filename the report was saved to.
    """
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"root_cause_analysis_report_{timestamp}.json"

    report_data = analysis_summary.copy()

    if "data_summary" in report_data and "date_range" in report_data["data_summary"]:
        date_range = report_data["data_summary"]["date_range"]
        if isinstance(date_range.get("start"), datetime):
            date_range["start"] = date_range["start"].strftime("%Y-%m-%d")
        if isinstance(date_range.get("end"), datetime):
            date_range["end"] = date_range["end"].strftime("%Y-%m-%d")

    with open(filename, "w") as f:
        json.dump(report_data, f, indent=2, default=str)

    logger.info("Report saved to: %s", filename)
    return filename
