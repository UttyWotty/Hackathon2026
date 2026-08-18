"""
ROI Executive Summary Generator for Manufacturing Analytics.
Extracts ROI-specific summary logic into a standalone function that builds
KPI dashboards, insights, and recommendations from ROI analysis results.
This module is consumed by SummaryGenerator for ROI report generation.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional

from .summary_templates import (
    create_insight,
    create_kpi_card,
    create_recommendation,
    get_base_template,
)

logger = logging.getLogger(__name__)

# Threshold constants for ROI performance classification
EFFICIENCY_EXCELLENT_THRESHOLD: float = 90.0
EFFICIENCY_GOOD_THRESHOLD: float = 80.0
UPTIME_TARGET_THRESHOLD: float = 80.0
WITHIN_CT_TARGET_THRESHOLD: float = 85.0
WITHIN_CT_CRITICAL_THRESHOLD: float = 75.0


def _build_roi_kpis(metrics: Dict[str, Any]) -> str:
    """
    Build KPI cards HTML for ROI summary.

    Args:
        metrics: Dictionary of ROI metric values.

    Returns:
        HTML string containing the KPI grid.
    """
    kpis_html = '<div class="kpi-grid">'

    avg_efficiency = metrics.get("avg_efficiency", metrics.get("average_efficiency", 0))
    kpis_html += create_kpi_card(
        label="Efficiency",
        value=f"{avg_efficiency:.1f}",
        unit="%",
        change="Target Duration Performance",
        change_type=(
            "positive"
            if avg_efficiency >= EFFICIENCY_EXCELLENT_THRESHOLD
            else "neutral"
        ),
    )

    total_shots = metrics.get("total_shots", 0)
    kpis_html += create_kpi_card(
        label="Total Shots",
        value=f"{total_shots:,}",
        unit="",
        change=f"{metrics.get('total_equipment', 1)} Equipment",
        change_type="neutral",
    )

    uptime_pct = metrics.get(
        "avg_uptime_percentage", metrics.get("uptime_percentage", 0)
    )
    kpis_html += create_kpi_card(
        label="Uptime",
        value=f"{uptime_pct:.1f}",
        unit="%",
        change="Production Uptime",
        change_type="positive" if uptime_pct >= UPTIME_TARGET_THRESHOLD else "warning",
    )

    within_target_pct = metrics.get("within_ct_percentage", 0)
    kpis_html += create_kpi_card(
        label="Within Target Duration",
        value=f"{within_target_pct:.1f}",
        unit="%",
        change="Shot Quality",
        change_type=(
            "positive" if within_target_pct >= WITHIN_CT_TARGET_THRESHOLD else "neutral"
        ),
    )

    kpis_html += "</div>"
    return kpis_html


def _build_roi_insights(metrics: Dict[str, Any]) -> str:
    """
    Build insights HTML section for ROI summary.

    Args:
        metrics: Dictionary of ROI metric values.

    Returns:
        HTML string containing the insights list.
    """
    avg_efficiency = metrics.get("avg_efficiency", metrics.get("average_efficiency", 0))
    within_target_pct = metrics.get("within_ct_percentage", 0)
    uptime_pct = metrics.get(
        "avg_uptime_percentage", metrics.get("uptime_percentage", 0)
    )
    total_shots = metrics.get("total_shots", 0)

    insights_html = '<ul class="insight-list">'

    # Efficiency insight
    if avg_efficiency >= EFFICIENCY_EXCELLENT_THRESHOLD:
        insights_html += create_insight(
            title="Excellent Duration Performance",
            description=(
                f"Equipment maintains {avg_efficiency:.1f}% efficiency with "
                f"{within_target_pct:.1f}% of shots within target duration range. "
                "This indicates strong process control and minimal duration variance."
            ),
            severity="info",
        )
    elif avg_efficiency >= EFFICIENCY_GOOD_THRESHOLD:
        insights_html += create_insight(
            title="Good Duration Performance with Room for Improvement",
            description=(
                f"Current efficiency of {avg_efficiency:.1f}% is solid but has "
                f"optimization potential. Focus on reducing shots outside target "
                f"CT range (currently {100 - within_target_pct:.1f}%)."
            ),
            severity="warning",
        )
    else:
        insights_html += create_insight(
            title="Duration Performance Requires Attention",
            description=(
                f"Efficiency of {avg_efficiency:.1f}% is below target. Only "
                f"{within_target_pct:.1f}% of shots within target duration. Investigate "
                "process issues, tooling condition, or material consistency."
            ),
            severity="critical",
        )

    # Uptime insight
    idle_pct = 100 - uptime_pct
    if uptime_pct >= UPTIME_TARGET_THRESHOLD:
        insights_html += create_insight(
            title=f"Strong Uptime: {uptime_pct:.1f}%",
            description=(
                f"Equipment uptime of {uptime_pct:.1f}% indicates {idle_pct:.1f}% "
                "idle time. Monitor for patterns in idle periods that could be "
                "optimized through better scheduling or reduced changeover times."
            ),
            severity="info",
        )
    else:
        insights_html += create_insight(
            title=f"Uptime Below Target: {uptime_pct:.1f}%",
            description=(
                f"Significant idle time detected ({idle_pct:.1f}%). Review "
                "production scheduling, material availability, and changeover "
                "procedures to improve equipment utilization."
            ),
            severity="warning",
        )

    # Production volume insight
    insights_html += create_insight(
        title=f"Production Volume: {total_shots:,} Shots",
        description=(
            f"Total production of {total_shots:,} shots across analysis period. "
            "This represents the baseline for planning and improvement "
            "ROI calculations."
        ),
        severity="info",
    )

    insights_html += "</ul>"
    return insights_html


def _build_roi_recommendations(metrics: Dict[str, Any]) -> str:
    """
    Build recommendations HTML section for ROI summary.

    Args:
        metrics: Dictionary of ROI metric values.

    Returns:
        HTML string containing the recommendations.
    """
    avg_efficiency = metrics.get("avg_efficiency", metrics.get("average_efficiency", 0))
    within_target_pct = metrics.get("within_ct_percentage", 0)
    uptime_pct = metrics.get(
        "avg_uptime_percentage", metrics.get("uptime_percentage", 0)
    )
    idle_pct = 100 - uptime_pct

    recommendations_html = ""

    if uptime_pct < UPTIME_TARGET_THRESHOLD:
        recommendations_html += create_recommendation(
            title="1. Reduce Idle Time Between Production Runs",
            description=(
                f"Current uptime of {uptime_pct:.1f}% leaves {idle_pct:.1f}% idle. "
                "Implement automated changeover procedures, pre-stage materials, "
                "and optimize scheduling to increase utilization by 10-15 "
                "percentage points."
            ),
            impact="+10-15% throughput",
            priority="high",
        )

    if within_target_pct < WITHIN_CT_TARGET_THRESHOLD:
        recommendations_html += create_recommendation(
            title="2. Improve Duration Consistency",
            description=(
                f"Only {within_target_pct:.1f}% of shots within target duration. Investigate "
                "root causes: tooling wear, material variability, process parameter "
                "drift. Target 90%+ within-spec rate."
            ),
            impact="+5-10% efficiency",
            priority=(
                "high" if within_target_pct < WITHIN_CT_CRITICAL_THRESHOLD else "medium"
            ),
        )

    if avg_efficiency >= EFFICIENCY_EXCELLENT_THRESHOLD:
        recommendations_html += create_recommendation(
            title="Maintain Current Performance Excellence",
            description=(
                f"Current {avg_efficiency:.1f}% efficiency is excellent. Continue "
                "preventive maintenance schedule, monitor for any degradation "
                "trends, and document best practices for replication across "
                "other equipment."
            ),
            impact="Sustain high performance",
            priority="medium",
        )

    return recommendations_html


def generate_roi_summary(
    analysis_result: Dict[str, Any],
    output_path: str,
    llm_insights: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generate executive summary HTML for ROI analysis.

    Builds a complete HTML report with KPI dashboard, executive insights,
    recommended actions, and optional AI-generated analysis section.

    Args:
        analysis_result: ROI analysis result dictionary containing metrics,
            machine_ids, vendor_names, date_range, and aggregation_level.
        output_path: Output HTML file path.
        llm_insights: Optional insights text from LLM analysis.

    Returns:
        Dictionary with status, summary_html_path, and message on success,
        or status and error on failure.
    """
    try:
        metrics = analysis_result.get("metrics", {})

        # Extract metadata
        machine_ids = analysis_result.get("machine_ids", ["N/A"])
        equipment_str = (
            ", ".join(machine_ids)
            if isinstance(machine_ids, list)
            else str(machine_ids)
        )

        vendor_names = analysis_result.get("vendor_names", ["N/A"])
        supplier_str = (
            ", ".join(vendor_names)
            if isinstance(vendor_names, list)
            else str(vendor_names)
        )

        metadata = {
            "Equipment": equipment_str,
            "Supplier": supplier_str,
            "Date Range": analysis_result.get("date_range", "N/A"),
            "Aggregation": analysis_result.get("aggregation_level", "daily").title(),
        }

        # Build sections
        kpis_html = _build_roi_kpis(metrics)
        insights_html = _build_roi_insights(metrics)
        recommendations_html = _build_roi_recommendations(metrics)

        # Add LLM insights if provided
        llm_section = ""
        if llm_insights:
            llm_section = (
                '<section class="section">'
                '<h2 class="section-title">AI-Generated Analysis</h2>'
                '<div class="insight-item">'
                f'<div class="insight-description">{llm_insights}</div>'
                "</div>"
                "</section>"
            )

        # Assemble content
        content = (
            '<section class="section">'
            '<h2 class="section-title">Key Performance Indicators</h2>'
            f"{kpis_html}"
            "</section>"
            '<section class="section">'
            '<h2 class="section-title">Executive Insights</h2>'
            f"{insights_html}"
            "</section>"
            '<section class="section">'
            '<h2 class="section-title">Recommended Actions</h2>'
            f"{recommendations_html}"
            "</section>"
            f"{llm_section}"
        )

        # Generate HTML
        html = get_base_template(
            title="ROI Analysis - Executive Summary",
            subtitle=f"{equipment_str} - {analysis_result.get('date_range', 'N/A')}",
            content=content,
            metadata=metadata,
        )

        # Write file
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html)

        logger.info("Executive summary generated: %s", output_path_obj.name)

        return {
            "status": "success",
            "summary_html_path": str(output_path),
            "message": f"Executive summary generated: {output_path_obj.name}",
        }

    except Exception as e:
        logger.error("Failed to generate ROI summary: %s", str(e))
        return {"status": "error", "error": f"Failed to generate summary: {str(e)}"}
