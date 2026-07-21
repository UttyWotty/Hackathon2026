"""
SQUAD Presentation PPT Builder - main orchestrator.
Assembles all slide factories into a complete sales presentation
matching the eMoldino SQUAD format with dynamic data from analyses.
"""

import logging
import os
from datetime import datetime
from typing import Any, Dict, List

from analysis.shared.ppt_generator import PPTGenerator
from services.sales_report.config import SalesReportConfig
from services.sales_report.data_aggregator import (
    compute_executive_totals,
    compute_tool_savings,
)
from services.sales_report.slide_factories.appendix_divider_slide import (
    add_appendix_divider_slide,
)
from services.sales_report.slide_factories.cover_slide import add_cover_slide
from services.sales_report.slide_factories.executive_summary_slide import (
    add_executive_summary_slide,
)
from services.sales_report.slide_factories.recommendations_slide import (
    add_recommendations_slide,
)
from services.sales_report.slide_factories.run_deep_dive_slide import (
    add_run_deep_dive_slide,
)
from services.sales_report.slide_factories.run_rate_chart_slide import (
    add_run_rate_chart_slide,
)
from services.sales_report.slide_factories.run_rate_efficiency_slide import (
    add_run_rate_efficiency_slide,
)
from services.sales_report.slide_factories.toc_slide import add_toc_slide
from services.sales_report.slide_factories.weekly_performance_slide import (
    add_weekly_performance_slide,
)

logger = logging.getLogger(__name__)

# -- Output directory --
DEFAULT_OUTPUT_DIR: str = "output/sales_reports"


def build_squad_presentation(
    config: SalesReportConfig,
    aggregated_data: Dict[str, Any],
    output_dir: str = DEFAULT_OUTPUT_DIR,
) -> str:
    """
    Build a complete SQUAD sales presentation from config and analysis data.

    Assembles slides in the standard order: cover, TOC, executive summary,
    recommendations, appendix divider, then per-tool deep dives with
    efficiency tables, weekly performance, and chart slides.

    Args:
        config: Complete sales report configuration.
        aggregated_data: Output from aggregate_all_data() containing
            roi, runrate, and capacity results keyed by equipment_code.
        output_dir: Directory to save the generated PPT file.

    Returns:
        Path to the generated .pptx file.
    """
    ppt = PPTGenerator()
    roi_data = aggregated_data.get("roi", {})
    runrate_data = aggregated_data.get("runrate", {})
    capacity_data = aggregated_data.get("capacity", {})

    # Compute per-tool savings (translates raw metrics to dollar values)
    all_savings: Dict[str, Dict[str, Any]] = {}
    for tool_cfg in config.tools:
        code = tool_cfg.equipment_code
        all_savings[code] = compute_tool_savings(
            tool_cfg=tool_cfg,
            roi_result=roi_data.get(code, {}),
            runrate_result=runrate_data.get(code, {}),
            capacity_result=capacity_data.get(code, {}),
            config=config,
        )

    # Compute executive totals from savings
    totals = compute_executive_totals(all_savings, config)

    # Format date label
    report_date_label = _format_report_date(config)

    # -- Section 1: Front matter --
    add_cover_slide(ppt, config, report_date_label)
    add_toc_slide(ppt, config)

    # -- Section 2: Executive Summary --
    add_executive_summary_slide(ppt, config, totals)

    # -- Section 3: Business Recommendations --
    add_recommendations_slide(ppt, config, totals)

    # -- Section 4: Appendix divider --
    add_appendix_divider_slide(ppt, config)

    # -- Section 5: Per-tool slides --
    for idx, tool_cfg in enumerate(config.tools):
        code = tool_cfg.equipment_code
        slide_num_base = 7 + (idx * 4)
        savings = all_savings.get(code, {})

        # Deep Dive (screenshot + savings metrics)
        add_run_deep_dive_slide(
            ppt,
            config,
            tool_cfg,
            savings,
            slide_number=str(slide_num_base).zfill(2),
        )

        # Run Rate Efficiency table
        add_run_rate_efficiency_slide(
            ppt,
            config,
            tool_cfg,
            savings,
            slide_number=str(slide_num_base + 1).zfill(2),
        )

        # Weekly Performance comparison
        weekly_kpis = _extract_weekly_kpis(
            runrate_data.get(code, {}),
            capacity_data.get(code, {}),
            savings,
            config,
        )
        month_label = report_date_label
        add_weekly_performance_slide(
            ppt,
            config,
            tool_cfg,
            weekly_kpis,
            month_label,
        )

        # Run Rate Cycle Time chart
        rr_result = runrate_data.get(code, {})
        add_run_rate_chart_slide(
            ppt,
            config,
            tool_cfg,
            rr_result,
            date_label=config.end_date,
        )

    # Save
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{config.client_slug}_squad_presentation_{timestamp}.pptx"
    output_path = os.path.join(output_dir, filename)
    saved_path = ppt.save(output_path)

    logger.info("SQUAD presentation saved to %s", saved_path)
    return saved_path


def _format_report_date(config: SalesReportConfig) -> str:
    """
    Format the report date label from the date range.

    Args:
        config: Sales report configuration.

    Returns:
        Formatted string like 'January - March, 2026' or 'March, 2026'.
    """
    if not config.end_date:
        return ""
    try:
        end_dt = datetime.strptime(config.end_date, "%Y-%m-%d")
        if config.start_date:
            start_dt = datetime.strptime(config.start_date, "%Y-%m-%d")
            if start_dt.month != end_dt.month or start_dt.year != end_dt.year:
                return f"{start_dt.strftime('%B')} - " f"{end_dt.strftime('%B, %Y')}"
        return end_dt.strftime("%B, %Y")
    except ValueError:
        return config.end_date


def _extract_weekly_kpis(
    runrate_result: Dict[str, Any],
    capacity_result: Dict[str, Any],
    savings: Dict[str, Any],
    config: SalesReportConfig,
) -> List[Dict[str, Any]]:
    """
    Extract weekly KPI data from runrate and capacity results.

    Maps raw analysis metric keys to the standardized KPI keys
    expected by weekly_performance_slide.

    Args:
        runrate_result: RunRate analysis result for one tool.
        capacity_result: Capacity analysis result for one tool.
        savings: Pre-computed savings for this tool.
        config: Sales report config for cost calculations.

    Returns:
        List of up to 4 weekly KPI dictionaries.
    """
    weekly_data = runrate_result.get("weekly_breakdown", [])
    if weekly_data:
        return weekly_data

    # Fallback: wrap combined metrics as a single "week"
    rr_metrics = runrate_result.get("metrics", {})
    cap_metrics = capacity_result.get("metrics", {})

    if not rr_metrics and not cap_metrics:
        return []

    # Map to standardized KPI keys for the slide factory
    downtime_hours = savings.get("downtime_hours", 0)
    kpi = {
        "loss_hours": downtime_hours,
        "incurred_costs": downtime_hours * config.total_cost_per_hour,
        "parts_opportunity_lost": savings.get("parts_lost", 0),
        "efficiency_percentage": rr_metrics.get("efficiency_percentage", 0),
        "mtbf_minutes": savings.get("mtbf_minutes", 0),
        "mttr_minutes": savings.get("mttr_minutes", 0),
        # Capacity
        "optimal_output": cap_metrics.get("total_optimal_output", 0),
        "actual_output": cap_metrics.get("total_actual_output", 0),
        "availability_loss": -(cap_metrics.get("total_gap", 0)),
        "efficiency_loss": 0,
    }

    return [kpi]
