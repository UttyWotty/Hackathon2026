"""
Data aggregator for sales report generation.
Calls existing analytics tools (ROI, RunRate, Capacity) and structures
the results into a unified dictionary ready for slide factories.
"""

import logging
from typing import Any, Dict

from services.config.features.analytics.tools.capacity_tools import (
    run_capacity_analysis,
)
from services.config.features.analytics.tools.roi_tools import run_roi_analysis
from services.config.features.analytics.tools.runrate_tools import run_runrate_analysis

from .config import SalesReportConfig, ToolConfig

logger = logging.getLogger(__name__)


# -- Result keys --
KEY_STATUS: str = "status"
KEY_METRICS: str = "metrics"
KEY_SESSION_DATA: str = "session_data"
KEY_ERROR: str = "error"
STATUS_SUCCESS: str = "success"
STATUS_ERROR: str = "error"

# -- Seconds per hour for conversions --
SECONDS_PER_HOUR: int = 3600


async def fetch_roi_for_tools(
    config: SalesReportConfig,
) -> Dict[str, Any]:
    """
    Run ROI analysis for all selected equipment codes.

    Args:
        config: Sales report configuration with tool list and date range.

    Returns:
        Dictionary keyed by equipment_code with ROI analysis results.
    """
    results: Dict[str, Any] = {}
    for tool_cfg in config.tools:
        code = tool_cfg.equipment_code
        try:
            logger.info("Fetching ROI for %s", code)
            result = await run_roi_analysis(
                equipment_codes=[code],
                start_date=config.start_date,
                end_date=config.end_date,
                client=config.client_name,
                aggregation_level="monthly",
            )
            results[code] = result
        except Exception as exc:
            logger.error("ROI analysis failed for %s: %s", code, exc)
            results[code] = {KEY_STATUS: STATUS_ERROR, KEY_ERROR: str(exc)}
    return results


async def fetch_runrate_for_tools(
    config: SalesReportConfig,
) -> Dict[str, Any]:
    """
    Run RunRate analysis for all selected equipment codes.

    Args:
        config: Sales report configuration with tool list and date range.

    Returns:
        Dictionary keyed by equipment_code with RunRate analysis results.
    """
    results: Dict[str, Any] = {}
    for tool_cfg in config.tools:
        code = tool_cfg.equipment_code
        try:
            logger.info("Fetching RunRate for %s", code)
            result = await run_runrate_analysis(
                equipment_codes=[code],
                start_date=config.start_date,
                end_date=config.end_date,
                client=config.client_name,
            )
            results[code] = result
        except Exception as exc:
            logger.error("RunRate analysis failed for %s: %s", code, exc)
            results[code] = {KEY_STATUS: STATUS_ERROR, KEY_ERROR: str(exc)}
    return results


async def fetch_capacity_for_tools(
    config: SalesReportConfig,
) -> Dict[str, Any]:
    """
    Run Capacity analysis for all selected equipment codes.

    Args:
        config: Sales report configuration with tool list and date range.

    Returns:
        Dictionary keyed by equipment_code with Capacity analysis results.
    """
    results: Dict[str, Any] = {}
    for tool_cfg in config.tools:
        code = tool_cfg.equipment_code
        try:
            logger.info("Fetching Capacity for %s", code)
            result = await run_capacity_analysis(
                equipment_codes=[code],
                start_date=config.start_date,
                end_date=config.end_date,
                client=config.client_name,
            )
            results[code] = result
        except Exception as exc:
            logger.error("Capacity analysis failed for %s: %s", code, exc)
            results[code] = {KEY_STATUS: STATUS_ERROR, KEY_ERROR: str(exc)}
    return results


async def aggregate_all_data(
    config: SalesReportConfig,
) -> Dict[str, Any]:
    """
    Fetch all analysis data needed for the SQUAD presentation.

    Calls ROI, RunRate, and Capacity analyses for every selected tool,
    then packages the results into a single dictionary.

    Args:
        config: Complete sales report configuration.

    Returns:
        Dictionary with keys 'roi', 'runrate', 'capacity', each mapping
        equipment_code to analysis results.
    """
    logger.info(
        "Aggregating data for %s (%d tools)",
        config.client_name,
        len(config.tools),
    )

    roi_data = await fetch_roi_for_tools(config)
    runrate_data = await fetch_runrate_for_tools(config)
    capacity_data = await fetch_capacity_for_tools(config)

    return {
        "roi": roi_data,
        "runrate": runrate_data,
        "capacity": capacity_data,
        "config": config,
    }


def compute_tool_savings(
    tool_cfg: ToolConfig,
    roi_result: Dict[str, Any],
    runrate_result: Dict[str, Any],
    capacity_result: Dict[str, Any],
    config: SalesReportConfig,
) -> Dict[str, Any]:
    """
    Compute dollar-value savings for a single tool.

    Translates raw analysis metrics into financial values using cost
    assumptions (machine rate, labor cost, part cost).

    Actual metric keys from analysis tools:
    - ROI: avg_efficiency, total_shots, within_ct_percentage, avg_uptime_percentage
    - RunRate: total_shots, total_stops, efficiency, mttr, mtbf,
               total_downtime_minutes, total_production_minutes
    - Capacity: total_actual_output, total_optimal_output, total_gap,
                avg_oee_100, avg_availability, avg_performance

    Args:
        tool_cfg: Tool configuration with part cost.
        roi_result: ROI analysis result.
        runrate_result: RunRate analysis result.
        capacity_result: Capacity analysis result.
        config: Sales report config for cost rates.

    Returns:
        Dictionary with part_loss_roi, time_loss_roi, ct_opportunity,
        total_savings, downtime_hours, production_hours, parts_lost, etc.
    """
    part_cost = tool_cfg.resolved_part_cost()
    cost_per_hour = config.total_cost_per_hour

    roi_metrics = roi_result.get(KEY_METRICS, {})
    rr_metrics = runrate_result.get(KEY_METRICS, {})
    cap_metrics = capacity_result.get(KEY_METRICS, {})

    # Parts lost = gap between optimal and actual output (from capacity)
    optimal_output = cap_metrics.get("total_optimal_output", 0)
    actual_output = cap_metrics.get("total_actual_output", 0)
    parts_lost = max(0, optimal_output - actual_output)

    # Part loss ROI = parts lost * part cost
    part_loss_roi = parts_lost * part_cost

    # Downtime from RunRate (in minutes -> hours)
    downtime_minutes = rr_metrics.get("downtime_minutes", 0)
    downtime_hours = downtime_minutes / 60.0

    # Time loss ROI = downtime hours * (machine rate + labor)
    time_loss_roi = downtime_hours * cost_per_hour

    # CT opportunity: efficiency gap from ROI
    # If efficiency < 100%, the gap represents CT savings potential
    efficiency_pct = roi_metrics.get(
        "avg_efficiency", roi_metrics.get("efficiency_avg", 100.0)
    )
    total_shots = rr_metrics.get("total_shots", 0)
    approved_ct = tool_cfg.contracted_ct_seconds or 0
    if approved_ct > 0 and efficiency_pct < 100.0:
        # Excess seconds per shot * total shots / 3600 * cost_per_hour
        excess_pct = max(0, (100.0 - efficiency_pct)) / 100.0
        excess_hours = (excess_pct * approved_ct * total_shots) / SECONDS_PER_HOUR
        ct_opportunity = excess_hours * cost_per_hour
    else:
        ct_opportunity = 0.0

    total_savings = part_loss_roi + time_loss_roi + ct_opportunity

    # Production time from RunRate
    production_minutes = rr_metrics.get("production_time_minutes", 0)
    production_hours = production_minutes / 60.0

    return {
        "part_loss_roi": part_loss_roi,
        "time_loss_roi": time_loss_roi,
        "ct_opportunity": ct_opportunity,
        "total_savings": total_savings,
        "parts_lost": parts_lost,
        "downtime_hours": downtime_hours,
        "downtime_minutes": downtime_minutes,
        "production_hours": production_hours,
        "production_minutes": production_minutes,
        "total_shots": total_shots,
        "efficiency_pct": efficiency_pct,
        "optimal_output": optimal_output,
        "actual_output": actual_output,
        # RunRate KPIs
        "run_rate_efficiency": rr_metrics.get("efficiency_percentage", 0),
        "total_stops": rr_metrics.get("total_stops", 0),
        "total_sessions": rr_metrics.get("total_sessions", 0),
        "normal_shots": rr_metrics.get("normal_shots", 0),
        # MTTR/MTBF computed from aggregate numbers
        "mttr_minutes": _compute_mttr(rr_metrics),
        "mtbf_minutes": _compute_mtbf(rr_metrics),
        # Capacity KPIs
        "oee_score": cap_metrics.get("avg_oee_100", 0),
        "availability": cap_metrics.get("avg_availability", 0),
        "performance": cap_metrics.get("avg_performance", 0),
        "quality": cap_metrics.get("avg_quality", 0),
        "capacity_gap": cap_metrics.get("total_gap", 0),
    }


def _compute_mttr(rr_metrics: Dict[str, Any]) -> float:
    """
    Compute Mean Time To Repair from aggregate RunRate metrics.

    MTTR = total downtime / number of stops.

    Args:
        rr_metrics: RunRate metrics dict.

    Returns:
        MTTR in minutes, or 0 if no stops.
    """
    downtime_min = rr_metrics.get("downtime_minutes", 0)
    total_stops = rr_metrics.get("total_stops", 0)
    if total_stops > 0 and downtime_min > 0:
        return downtime_min / total_stops
    return 0.0


def _compute_mtbf(rr_metrics: Dict[str, Any]) -> float:
    """
    Compute Mean Time Between Failures from aggregate RunRate metrics.

    MTBF = total production time / number of stops.

    Args:
        rr_metrics: RunRate metrics dict.

    Returns:
        MTBF in minutes, or 0 if no stops.
    """
    production_min = rr_metrics.get("production_time_minutes", 0)
    total_stops = rr_metrics.get("total_stops", 0)
    if total_stops > 0 and production_min > 0:
        return production_min / total_stops
    return 0.0


def compute_executive_totals(
    all_savings: Dict[str, Dict[str, Any]],
    config: SalesReportConfig,
) -> Dict[str, Any]:
    """
    Compute aggregate ROI totals for the executive summary slide.

    Sums part loss ROI, time loss ROI, CT opportunity, and total savings
    across all tools. Computes overall ROI ratio against project cost.

    Args:
        all_savings: Per-tool savings from compute_tool_savings().
        config: Sales report config (for project_cost).

    Returns:
        Dictionary with total_savings, part_loss_roi, time_loss_roi,
        ct_opportunity, project_cost, roi_ratio.
    """
    total_savings: float = 0.0
    part_loss_roi: float = 0.0
    time_loss_roi: float = 0.0
    ct_opportunity: float = 0.0

    for code, savings in all_savings.items():
        part_loss_roi += savings.get("part_loss_roi", 0.0)
        time_loss_roi += savings.get("time_loss_roi", 0.0)
        ct_opportunity += savings.get("ct_opportunity", 0.0)

    total_savings = part_loss_roi + time_loss_roi + ct_opportunity
    roi_ratio = total_savings / config.project_cost if config.project_cost > 0 else 0.0

    return {
        "total_savings": total_savings,
        "part_loss_roi": part_loss_roi,
        "time_loss_roi": time_loss_roi,
        "ct_opportunity": ct_opportunity,
        "project_cost": config.project_cost,
        "roi_ratio": roi_ratio,
    }
