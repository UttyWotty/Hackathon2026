"""Weekly Comparison PowerPoint Generator for manufacturing KPI reports.

This module orchestrates the generation of newsletter-style weekly comparison
presentations, including metric extraction, KPI calculation, and slide assembly.
Slide building and insight generation are delegated to dedicated submodules.
"""

import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from analysis.shared.ppt_generator import PPTGenerator
from analysis.shared.ppt_insight_generators import generate_key_insights
from analysis.shared.ppt_slide_builders import (
    LABEL_WEEK_1,
    LABEL_WEEK_2,
    add_capacity_details_slide,
    add_kpi_comparison_table,
)

# Cost constants
MACHINE_RATE_PER_HOUR = 170.0  # $170/h
LABOR_COST_PER_HOUR = 10.0  # $10/h
TOTAL_COST_PER_HOUR = MACHINE_RATE_PER_HOUR + LABOR_COST_PER_HOUR


def calculate_percentage_change(current: float, previous: float) -> str:
    """Calculate percentage change formatted as {+X.XX%} or {-X.XX%}.

    Args:
        current: Current week value
        previous: Previous week value

    Returns:
        Formatted percentage change string
    """
    if previous == 0:
        return "{N/A}"
    change = ((current - previous) / previous) * 100
    sign = "+" if change >= 0 else ""
    return f"{{{sign}{change:.2f}%}}"


def calculate_cost_from_hours(loss_hours: float) -> float:
    """Calculate total cost from machine hours lost.

    Args:
        loss_hours: Number of hours lost

    Returns:
        Total cost in dollars
    """
    return loss_hours * TOTAL_COST_PER_HOUR


def _get_initial_mttr_mtbf(metrics: Dict[str, Any]) -> Tuple[float, float]:
    """Get initial MTTR and MTBF values from metrics dictionary.

    Args:
        metrics: Metrics dictionary

    Returns:
        Tuple of (mttr_minutes, mtbf_minutes)
    """
    mtbf_minutes = metrics.get("mtbf_minutes") or (metrics.get("mtbf_hours", 0) * 60)
    mttr_minutes = metrics.get("mttr_minutes") or metrics.get(
        "average_stop_duration_minutes", 0
    )
    return mttr_minutes, mtbf_minutes


def _filter_main_sessions(df_sessions: Any) -> Any:
    """Filter sessions to include only main sessions (>= 3 shots).

    Args:
        df_sessions: DataFrame with session data

    Returns:
        DataFrame with filtered sessions
    """
    if "total_shots" in df_sessions.columns:
        main_sessions = df_sessions[df_sessions["total_shots"] >= 3]
    else:
        main_sessions = df_sessions

    # If all sessions filtered out, use all sessions (edge case)
    if main_sessions.empty:
        main_sessions = df_sessions

    return main_sessions


def _calculate_mttr_from_sessions(main_sessions: Any, mttr_minutes: float) -> float:
    """Calculate MTTR from session data.

    Args:
        main_sessions: DataFrame with filtered session data
        mttr_minutes: Current MTTR value (may be 0)

    Returns:
        Calculated MTTR in minutes
    """
    # Use actual MTTR from session data if available
    if "mttr_minutes" in main_sessions.columns:
        mttr_values = main_sessions["mttr_minutes"].dropna()
        if len(mttr_values) > 0:
            return float(mttr_values.mean())

    # Fallback: Calculate from aggregate downtime and stops
    if (
        mttr_minutes == 0
        and "downtime_minutes" in main_sessions.columns
        and "total_stops" in main_sessions.columns
    ):
        total_downtime = main_sessions["downtime_minutes"].sum()
        total_stops = main_sessions["total_stops"].sum()
        if total_stops > 0:
            return total_downtime / total_stops

    return mttr_minutes


def _calculate_mtbf_from_sessions(main_sessions: Any, mtbf_minutes: float) -> float:
    """Calculate MTBF from session data.

    Args:
        main_sessions: DataFrame with filtered session data
        mtbf_minutes: Current MTBF value (may be 0)

    Returns:
        Calculated MTBF in minutes
    """
    # Use actual MTBF from session data if available
    if "mtbf_minutes" in main_sessions.columns:
        mtbf_values = main_sessions["mtbf_minutes"].dropna()
        if len(mtbf_values) > 0:
            return float(mtbf_values.mean())

    # Fallback: Calculate from aggregate production time and stops
    if (
        mtbf_minutes == 0
        and "production_time_minutes" in main_sessions.columns
        and "total_stops" in main_sessions.columns
    ):
        total_prod_time = main_sessions["production_time_minutes"].sum()
        total_stops = main_sessions["total_stops"].sum()
        if total_stops > 0:
            return total_prod_time / total_stops

    return mtbf_minutes


def _process_session_data(
    session_data: List[Dict], mttr_minutes: float, mtbf_minutes: float
) -> Tuple[float, float]:
    """Process session data to calculate MTTR and MTBF.

    Args:
        session_data: List of session dictionaries
        mttr_minutes: Initial MTTR value
        mtbf_minutes: Initial MTBF value

    Returns:
        Tuple of (calculated_mttr_minutes, calculated_mtbf_minutes)
    """
    import pandas as pd  # type: ignore

    df_sessions = pd.DataFrame(session_data)
    main_sessions = _filter_main_sessions(df_sessions)

    mttr_minutes = _calculate_mttr_from_sessions(main_sessions, mttr_minutes)
    mtbf_minutes = _calculate_mtbf_from_sessions(main_sessions, mtbf_minutes)
    return mttr_minutes, mtbf_minutes


def _build_runrate_result_dict(
    metrics: Dict[str, Any], mttr_minutes: float, mtbf_minutes: float
) -> Dict[str, Any]:
    """Build the final result dictionary for RunRate metrics.

    Args:
        metrics: Original metrics dictionary
        mttr_minutes: Calculated MTTR in minutes
        mtbf_minutes: Calculated MTBF in minutes

    Returns:
        Dictionary with standardized RunRate metrics
    """
    good_shots = metrics.get("good_shots") or metrics.get("normal_shots", 0)
    total_shots = metrics.get("total_shots", 0)
    return {
        "efficiency_percent": metrics.get("efficiency_percentage")
        or metrics.get("efficiency_percent", 0),
        "mtbf_minutes": mtbf_minutes,
        "mttr_minutes": mttr_minutes,
        "total_shots": total_shots,
        "good_shots": good_shots,
        "bad_shots": total_shots - good_shots,
        "total_stops": metrics.get("total_stops", 0),
        "downtime_minutes": metrics.get("downtime_minutes")
        or (metrics.get("downtime_hours", 0) * 60),
    }


def extract_runrate_metrics(
    metrics: Dict[str, Any], session_data: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """Extract RunRate metrics in standardized format.

    Calculates MTTR/MTBF from session data if available (matches Excel calculation).
    Falls back to metrics dictionary if session data not available.

    Args:
        metrics: Metrics dictionary
        session_data: Optional list of session dictionaries

    Returns:
        Dictionary with standardized RunRate metrics
    """
    # Get initial MTTR/MTBF from metrics
    mttr_minutes, mtbf_minutes = _get_initial_mttr_mtbf(metrics)

    # If session data is available, calculate MTTR/MTBF from sessions
    if session_data and isinstance(session_data, list) and len(session_data) > 0:
        mttr_minutes, mtbf_minutes = _process_session_data(
            session_data, mttr_minutes, mtbf_minutes
        )

    return _build_runrate_result_dict(metrics, mttr_minutes, mtbf_minutes)


def extract_capacity_metrics(metrics: Dict[str, Any]) -> Dict[str, Any]:
    """Extract Capacity metrics in standardized format.

    Args:
        metrics: Raw capacity metrics dictionary

    Returns:
        Dictionary with standardized capacity metrics
    """
    # Calculate availability loss and performance loss from gap components
    gap = metrics.get("total_gap", 0)
    availability = metrics.get("avg_availability", 0)
    performance = metrics.get("avg_performance", 0)

    # Estimate losses (approximations based on OEE components)
    optimal_output = metrics.get("total_optimal_output", 0)
    availability_loss = (
        int((1 - availability) * optimal_output) if availability < 1 else 0
    )

    # Performance loss = gap - availability_loss (approximate)
    performance_loss = max(0, int(gap - availability_loss))
    return {
        "optimal_output_100_oee": optimal_output,
        "actual_output": metrics.get("total_actual_output", 0),
        "gap": gap,
        "availability": availability,
        "performance": performance,
        "quality": metrics.get("avg_quality", 0),
        "oee_score": metrics.get("avg_oee_100", 0),
        "availability_loss": availability_loss,
        "performance_loss": performance_loss,
    }


def calculate_weekly_kpis(
    runrate_metrics: Dict[str, Any],
    capacity_metrics: Dict[str, Any],
) -> Dict[str, Any]:
    """Calculate all weekly KPIs from analysis metrics.

    Args:
        runrate_metrics: Standardized RunRate metrics dictionary
        capacity_metrics: Standardized capacity metrics dictionary

    Returns:
        Dictionary with all KPIs formatted for comparison table
    """
    # Calculate loss hours from downtime
    loss_hours = runrate_metrics.get("downtime_minutes", 0) / 60.0

    # Calculate costs
    total_costs = calculate_cost_from_hours(loss_hours)

    # Parts opportunity lost = gap from capacity analysis
    parts_opportunity_lost = int(capacity_metrics.get("gap", 0))

    # RunRate metrics
    efficiency = runrate_metrics.get("efficiency_percent", 0)
    mtbf_minutes = runrate_metrics.get("mtbf_minutes", 0)
    mttr_minutes = runrate_metrics.get("mttr_minutes", 0)

    # Capacity metrics
    optimal_output = int(capacity_metrics.get("optimal_output_100_oee", 0))
    actual_output = int(capacity_metrics.get("actual_output", 0))
    availability_loss = int(capacity_metrics.get("availability_loss", 0))
    performance_loss = int(capacity_metrics.get("performance_loss", 0))

    # Efficiency gain/loss = performance loss (negative means loss)
    efficiency_gain_loss = -performance_loss

    return {
        "loss_machine_hours": round(loss_hours, 1),
        "total_costs": round(total_costs, 0),
        "parts_opportunity_lost": parts_opportunity_lost,
        "runrate_efficiency": round(efficiency, 1),
        "runrate_mtbf_minutes": round(mtbf_minutes, 0),
        "runrate_mttr_minutes": round(mttr_minutes, 0),
        "capacity_oee_score": (
            round(capacity_metrics.get("oee_score", 0) * 100, 1)
            if capacity_metrics.get("oee_score")
            else None
        ),
        "optimal_output": optimal_output,
        "actual_output": actual_output,
        "output_gap": optimal_output - actual_output,
        "availability_gain_loss": -availability_loss,
        "efficiency_gain_loss": efficiency_gain_loss,
    }


def _extract_week_metrics(
    week_data: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Extract runrate and capacity metrics from a single week's data.

    Args:
        week_data: Dictionary with 'runrate' and optionally 'capacity',
            'runrate_session_data', and 'session_metrics' keys

    Returns:
        Tuple of (runrate_metrics, capacity_metrics)
    """
    runrate_raw = week_data.get("runrate", {})
    session_data = week_data.get("runrate_session_data") or week_data.get(
        "session_metrics"
    )
    runrate = extract_runrate_metrics(runrate_raw, session_data)
    capacity = extract_capacity_metrics(week_data.get("capacity", {}))
    return runrate, capacity


def generate_weekly_comparison_ppt(
    equipment_code: str,
    supplier_name: Optional[str] = None,
    week1_data: Optional[Dict[str, Any]] = None,
    week2_data: Optional[Dict[str, Any]] = None,
    week1_dates: Optional[Tuple[str, str]] = None,
    week2_dates: Optional[Tuple[str, str]] = None,
    output_dir: str = "output/comparison",
) -> str:
    """Generate weekly comparison PowerPoint in newsletter format.

    Args:
        equipment_code: Equipment identifier
        supplier_name: Optional supplier/client name (defaults to equipment_code)
        week1_data: Dict with 'runrate' and 'capacity' metrics for week 1
        week2_data: Dict with 'runrate' and 'capacity' metrics for week 2
        week1_dates: (start_date, end_date) for week 1
        week2_dates: (start_date, end_date) for week 2
        output_dir: Output directory

    Returns:
        Path to generated PowerPoint file
    """
    ppt = PPTGenerator()

    # Handle None values
    if week1_data is None:
        week1_data = {}
    if week2_data is None:
        week2_data = {}

    # Extract metrics
    week1_runrate, week1_capacity = _extract_week_metrics(week1_data)
    week2_runrate, week2_capacity = _extract_week_metrics(week2_data)

    # Calculate KPIs
    week1_kpis = calculate_weekly_kpis(week1_runrate, week1_capacity)
    week2_kpis = calculate_weekly_kpis(week2_runrate, week2_capacity)

    # Slide 1: Title Slide
    title = "Weekly Performance Report"
    subtitle = f"{equipment_code}" + (f" - {supplier_name}" if supplier_name else "")
    metadata = {
        LABEL_WEEK_1: f"{week1_dates[0]} to {week1_dates[1]}",
        LABEL_WEEK_2: f"{week2_dates[0]} to {week2_dates[1]}",
    }
    ppt.add_title_slide(title, subtitle, metadata)

    # Slide 2: KPI Comparison Table
    add_kpi_comparison_table(
        ppt,
        equipment_code,
        week1_kpis,
        week2_kpis,
        calculate_percentage_change,
    )

    # Slide 3: Key Insights
    insights = generate_key_insights(
        equipment_code,
        week1_kpis,
        week2_kpis,
        week1_runrate,
        week2_runrate,
        week1_capacity,
        week2_capacity,
        calculate_percentage_change,
    )
    ppt.add_text_slide("Key Insights", insights, bullet=True)

    # Slide 4: Detailed Capacity Analysis
    add_capacity_details_slide(
        ppt,
        equipment_code,
        week1_kpis,
        week2_kpis,
        calculate_percentage_change,
    )

    # Save presentation
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"weekly_comparison_{equipment_code}_{timestamp}.pptx"
    output_path = os.path.join(output_dir, filename)
    return ppt.save(output_path)
