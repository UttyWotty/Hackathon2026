"""RunRate Analysis PowerPoint Generator
======================================

Creates presentation-ready PowerPoint from RunRate analysis results.

Features:
    - Executive summary with key metrics
    - Efficiency trends and charts
    - Session analysis
    - Recommendations
    - Professional formatting

Author: Utku Gulbardak
Date: 2025-11-28
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd  # type: ignore

from analysis.shared.ppt_generator import PPTGenerator, format_metric_value


def generate_runrate_ppt(
    metrics: Dict[str, Any],
    session_data: Optional[pd.DataFrame] = None,
    equipment_code: Optional[str] = None,
    supplier_name: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    output_dir: str = "output/runrate",
) -> str:
    """Generate PowerPoint presentation for RunRate analysis.

    Creates a professional presentation with:
        1. Title Slide
        2. Executive Summary (key metrics)
        3. Efficiency Metrics
        4. Production Analysis
        5. Session Analysis (if data provided)
        6. Recommendations

    Args:
        metrics: Analysis metrics dictionary
        session_data: Optional session-level data
        equipment_code: Equipment identifier
        supplier_name: Supplier name
        start_date: Analysis start date
        end_date: Analysis end date
        output_dir: Output directory for PPT file

    Returns:
        Path to generated PowerPoint file
    """
    # Initialize generator
    ppt = PPTGenerator()

    # Slide 1: Title Slide
    title = "RunRate Analysis Report"
    subtitle = f"{supplier_name or 'Manufacturing'} Operations"
    metadata = {}
    if equipment_code:
        metadata["Equipment"] = equipment_code
    if start_date and end_date:
        metadata["Period"] = f"{start_date} to {end_date}"
    elif start_date:
        metadata["Start Date"] = start_date
    elif end_date:
        metadata["End Date"] = end_date

    ppt.add_title_slide(title, subtitle, metadata)

    # Slide 2: Executive Summary
    summary_metrics = _extract_summary_metrics(metrics)
    ppt.add_summary_slide("Executive Summary", summary_metrics, layout="grid")

    # Slide 3: Efficiency Metrics
    efficiency_metrics = _extract_efficiency_metrics(metrics)
    ppt.add_summary_slide("Efficiency Metrics", efficiency_metrics, layout="list")

    # Slide 4: Production Analysis
    production_metrics = _extract_production_metrics(metrics)
    ppt.add_summary_slide("Production Analysis", production_metrics, layout="list")

    # Slide 5: Session Analysis (if data available)
    if session_data is not None and not session_data.empty:
        # Prepare session data for display
        display_columns = [
            col
            for col in [
                "SESSION_START",
                "SESSION_END",
                "SHOTS",
                "EFFICIENCY",
                "MTTR_MIN",
            ]
            if col in session_data.columns
        ]
        if display_columns:
            session_display = session_data[display_columns].copy()
            ppt.add_table_slide("Session Analysis", session_display, max_rows=8)

    # Slide 6: Key Findings & Recommendations
    findings = _generate_findings(metrics)
    ppt.add_text_slide("Key Findings & Recommendations", findings, bullet=True)

    # Slide 7: Appendix
    appendix_content = [
        "Data Sources:",
        "- Manufacturing database (Snowflake)",
        "- Real-time production monitoring",
        "",
        "Metrics Definitions:",
        "- Efficiency: (Good shots / Total shots) x 100%",
        "- MTTR: Mean Time To Repair (minutes)",
        "- MTBF: Mean Time Between Failures (hours)",
        "",
        "For detailed data, refer to the Excel report.",
    ]
    ppt.add_text_slide("Appendix", appendix_content, bullet=False)

    # Save presentation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"runrate_presentation_{equipment_code or 'analysis'}_{timestamp}.pptx"
    output_path = os.path.join(output_dir, filename)
    return ppt.save(output_path)


def _extract_summary_metrics(metrics: Dict[str, Any]) -> Dict[str, str]:
    """Extract key metrics for executive summary slide."""
    summary = {}

    # Efficiency
    if "efficiency_percent" in metrics:
        summary["Efficiency"] = f"{metrics['efficiency_percent']:.1f}%"
    elif "average_efficiency" in metrics:
        summary["Avg Efficiency"] = f"{metrics['average_efficiency']:.1f}%"

    # Total shots
    if "total_shots" in metrics:
        summary["Total Shots"] = format_metric_value(metrics["total_shots"])

    # Sessions
    if "total_sessions" in metrics:
        summary["Sessions"] = format_metric_value(metrics["total_sessions"])

    # MTTR
    if "mttr_minutes" in metrics:
        summary["MTTR"] = f"{metrics['mttr_minutes']:.1f} min"
    elif "average_stop_duration_minutes" in metrics:
        summary["Avg Stop"] = f"{metrics['average_stop_duration_minutes']:.1f} min"

    # MTBF
    if "mtbf_hours" in metrics:
        summary["MTBF"] = f"{metrics['mtbf_hours']:.1f} hrs"

    # Good shots
    if "good_shots" in metrics:
        summary["Good Shots"] = format_metric_value(metrics["good_shots"])

    return summary


def _extract_efficiency_metrics(metrics: Dict[str, Any]) -> Dict[str, str]:
    """Extract efficiency-related metrics."""
    efficiency = {}

    if "efficiency_percent" in metrics:
        efficiency["Overall Efficiency"] = f"{metrics['efficiency_percent']:.2f}%"
    if "average_efficiency" in metrics:
        efficiency["Average Efficiency"] = f"{metrics['average_efficiency']:.2f}%"
    if "best_session_efficiency" in metrics:
        efficiency["Best Session"] = f"{metrics['best_session_efficiency']:.2f}%"
    if "worst_session_efficiency" in metrics:
        efficiency["Worst Session"] = f"{metrics['worst_session_efficiency']:.2f}%"
    if "good_shots" in metrics and "total_shots" in metrics:
        good = metrics["good_shots"]
        total = metrics["total_shots"]
        bad = total - good
        efficiency["Good Shots"] = format_metric_value(good)
        efficiency["Bad Shots"] = format_metric_value(bad)

    return efficiency


def _extract_production_metrics(metrics: Dict[str, Any]) -> Dict[str, str]:
    """Extract production-related metrics."""
    production = {}

    if "total_shots" in metrics:
        production["Total Shots"] = format_metric_value(metrics["total_shots"])
    if "total_sessions" in metrics:
        production["Total Sessions"] = format_metric_value(metrics["total_sessions"])
    if "total_production_time_hours" in metrics:
        production["Production Time"] = (
            f"{metrics['total_production_time_hours']:.1f} hrs"
        )
    if "total_downtime_hours" in metrics:
        production["Downtime"] = f"{metrics['total_downtime_hours']:.1f} hrs"
    if "total_stop_events" in metrics:
        production["Stop Events"] = format_metric_value(metrics["total_stop_events"])
    if "average_stop_duration_minutes" in metrics:
        production["Avg Stop Duration"] = (
            f"{metrics['average_stop_duration_minutes']:.1f} min"
        )
    if "mttr_minutes" in metrics:
        production["MTTR"] = f"{metrics['mttr_minutes']:.1f} min"
    if "mtbf_hours" in metrics:
        production["MTBF"] = f"{metrics['mtbf_hours']:.1f} hrs"

    return production


def _generate_efficiency_finding(efficiency: float) -> str:
    """Generate efficiency finding based on efficiency percentage.

    Args:
        efficiency: Efficiency percentage value

    Returns:
        Formatted finding string
    """
    if efficiency >= 90:
        return (
            f"Excellent efficiency: {efficiency:.1f}% - Equipment performing optimally"
        )
    if efficiency >= 80:
        return f"-> Good efficiency: {efficiency:.1f}% - Minor improvements possible"
    if efficiency >= 70:
        return (
            f"Moderate efficiency: {efficiency:.1f}% - Review quality control processes"
        )
    return f"Low efficiency: {efficiency:.1f}% - Immediate action required"


def _generate_mttr_finding(mttr: float) -> str:
    """Generate MTTR finding based on mean time to repair.

    Args:
        mttr: MTTR in minutes

    Returns:
        Formatted finding string
    """
    if mttr < 30:
        return f"Quick repairs: MTTR {mttr:.1f} min - Maintenance team responsive"
    if mttr < 60:
        return f"-> Average repair time: MTTR {mttr:.1f} min - Within acceptable range"
    return f"Slow repairs: MTTR {mttr:.1f} min - Review maintenance procedures"


def _generate_mtbf_finding(mtbf: float) -> str:
    """Generate MTBF finding based on mean time between failures.

    Args:
        mtbf: MTBF in hours

    Returns:
        Formatted finding string
    """
    if mtbf > 100:
        return f"Reliable operation: MTBF {mtbf:.1f} hrs - Minimal failures"
    if mtbf > 50:
        return f"-> Moderate reliability: MTBF {mtbf:.1f} hrs - Preventive maintenance recommended"
    return f"Frequent failures: MTBF {mtbf:.1f} hrs - Investigate root causes"


def _get_general_recommendations() -> List[str]:
    """Get general recommendations for all reports.

    Returns:
        List of recommendation strings
    """
    return [
        "",
        "Recommendations:",
        "- Continue monitoring efficiency trends",
        "- Schedule preventive maintenance during low-demand periods",
        "- Review quality control procedures for bad shots",
        "- Analyze session data to identify patterns",
    ]


def _generate_findings(metrics: Dict[str, Any]) -> List[str]:
    """Generate key findings and recommendations based on metrics."""
    findings = []

    # Efficiency findings
    if "efficiency_percent" in metrics:
        findings.append(_generate_efficiency_finding(metrics["efficiency_percent"]))

    # MTTR findings
    if "mttr_minutes" in metrics:
        findings.append(_generate_mttr_finding(metrics["mttr_minutes"]))

    # MTBF findings
    if "mtbf_hours" in metrics:
        findings.append(_generate_mtbf_finding(metrics["mtbf_hours"]))

    # Production volume
    if "total_shots" in metrics:
        shots = metrics["total_shots"]
        findings.append(
            f"Production volume: {format_metric_value(shots)} shots processed"
        )

    # General recommendations
    findings.extend(_get_general_recommendations())

    return findings
